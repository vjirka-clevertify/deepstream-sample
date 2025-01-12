#!/usr/bin/env python3

import sys
import math
import gi
import pyds
import numpy as np
from collections import defaultdict
import os
import signal

gi.require_version("Gst", "1.0")
from gi.repository import GObject, Gst, GLib


class VehicleTracker:
    def __init__(self):
        self.vehicles = defaultdict(list)
        self.speeds = defaultdict(list)
        self.frame_rate = 30.0
        self.real_world_width = 15.0
        self.pixels_per_meter = 50.0
        self.max_tracking_history = 30

    def calculate_speed(self, positions, time_diff):
        if len(positions) < 2:
            return None
        pixel_distance = math.sqrt(
            (positions[-1][1] - positions[0][1]) ** 2
            + (positions[-1][2] - positions[0][2]) ** 2
        )
        distance = pixel_distance / self.pixels_per_meter
        speed = (distance / time_diff) * 3.6
        return speed

    def update_vehicle(self, obj_id, frame_num, bbox):
        self.vehicles[obj_id].append((frame_num, bbox.left, bbox.top))
        if len(self.vehicles[obj_id]) >= 2:
            time_diff = (
                self.vehicles[obj_id][-1][0] - self.vehicles[obj_id][0][0]
            ) / self.frame_rate
            speed = self.calculate_speed(self.vehicles[obj_id], time_diff)
            if speed:
                self.speeds[obj_id].append(speed)
        if len(self.vehicles[obj_id]) > self.max_tracking_history:
            self.vehicles[obj_id].pop(0)


def osd_sink_pad_buffer_probe(pad, info, u_data):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    tracker = u_data

    while l_frame:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        l_obj = frame_meta.obj_meta_list

        while l_obj:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            tracker.update_vehicle(
                obj_meta.object_id, frame_meta.frame_num, obj_meta.rect_params
            )

            if obj_meta.object_id in tracker.speeds:
                speed = tracker.speeds[obj_meta.object_id][-1]

                # Create display meta for this frame
                display_meta = pyds.nvds_acquire_display_meta_from_pool(
                    batch_meta
                )
                display_meta.num_labels = 1

                # Configure text parameters with type checking
                txt_params = display_meta.text_params[0]
                txt_params.display_text = (
                    f"ID:{obj_meta.object_id} {speed:.1f}km/h"
                )

                # Ensure positive coordinates for text position
                x_pos = max(0, int(obj_meta.rect_params.left))
                y_pos = max(10, int(obj_meta.rect_params.top))

                txt_params.x_offset = x_pos
                txt_params.y_offset = y_pos
                txt_params.font_params.font_name = "Arial"
                txt_params.font_params.font_size = 11
                txt_params.font_params.font_color.set(1.0, 1.0, 0.0, 1.0)
                txt_params.set_bg_clr = 1
                txt_params.text_bg_clr.set(0.0, 0.0, 0.0, 0.7)

                # Configure rectangle parameters
                rect_params = display_meta.rect_params[0]
                rect_params.left = obj_meta.rect_params.left
                rect_params.top = obj_meta.rect_params.top
                rect_params.width = obj_meta.rect_params.width
                rect_params.height = obj_meta.rect_params.height
                rect_params.border_width = 2
                rect_params.border_color.set(1.0, 0.0, 0.0, 1.0)
                display_meta.num_rects = 1

                # Add display meta to frame
                pyds.nvds_add_display_meta_to_frame(frame_meta, display_meta)

            l_obj = l_obj.next
        l_frame = l_frame.next

    return Gst.PadProbeReturn.OK


def setup_environment():
    DS_PATH = "/opt/nvidia/deepstream/deepstream-6.3"
    os.environ.update(
        {
            "GST_PLUGIN_PATH": f"{DS_PATH}/lib",
            "LD_LIBRARY_PATH": f"{DS_PATH}/lib",
            "PATH": f"{os.environ['PATH']}:/usr/local/cuda/bin",
        }
    )


def configure_tracker(tracker):
    DS_PATH = "/opt/nvidia/deepstream/deepstream-6.3"
    tracker_lib = f"{DS_PATH}/lib/libnvds_nvmultiobjecttracker.so"
    tracker_config = f"{DS_PATH}/deepstream-sample/config/tracker_config.txt"

    try:
        tracker.set_property("ll-lib-file", tracker_lib)
        tracker.set_property("ll-config-file", os.path.abspath(tracker_config))

        print(f"Tracker configured with library: {tracker_lib}")
        print(f"Using tracker config: {tracker_config}")

        # Verify the property was set
        config_path = tracker.get_property("ll-config-file")
        if not config_path:
            raise RuntimeError("Failed to set tracker config path")

    except Exception as e:
        raise RuntimeError(f"Failed to set tracker properties: {e}")


def get_state_name(state):
    state_names = {
        Gst.State.VOID_PENDING: "VOID_PENDING",
        Gst.State.NULL: "NULL",
        Gst.State.READY: "READY",
        Gst.State.PAUSED: "PAUSED",
        Gst.State.PLAYING: "PLAYING",
    }
    return state_names.get(state, "UNKNOWN")


def get_state_change_return(ret):
    return_names = {
        Gst.StateChangeReturn.SUCCESS: "SUCCESS",
        Gst.StateChangeReturn.FAILURE: "FAILURE",
        Gst.StateChangeReturn.ASYNC: "ASYNC",
        Gst.StateChangeReturn.NO_PREROLL: "NO_PREROLL",
    }
    return return_names.get(ret, "UNKNOWN")


def main():
    setup_environment()
    Gst.init(None)
    pipeline = Gst.Pipeline()

    # Create elements
    source = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    encoder = Gst.ElementFactory.make("nvv4l2h264enc", "h264-encoder")
    h264parse = Gst.ElementFactory.make("h264parse", "h264-parser")
    qtmux = Gst.ElementFactory.make("qtmux", "muxer")
    sink = Gst.ElementFactory.make("filesink", "file-output")

    output_path = "output.mp4"
    sink.set_property("location", output_path)

    try:
        configure_tracker(tracker)
    except RuntimeError as e:
        print(f"Failed to configure tracker: {e}")
        return -1

    if not all(
        [
            source,
            streammux,
            pgie,
            tracker,
            nvvidconv,
            nvosd,
            encoder,
            h264parse,
            qtmux,
            sink,
        ]
    ):
        sys.stderr.write(
            " One or more elements could not be created. Exiting.\n"
        )
        return -1

    source.set_property(
        "uri",
        "file:///opt/nvidia/deepstream/deepstream-6.3/deepstream-sample/deepstream_test1.mp4",
    )
    streammux.set_property("width", 1920)
    streammux.set_property("height", 1080)
    streammux.set_property("batch-size", 1)
    streammux.set_property("live-source", 0)
    streammux.set_property("nvbuf-memory-type", 0)
    streammux.set_property("frame-duration", 33333333)
    pgie.set_property(
        "config-file-path",
        "/opt/nvidia/deepstream/deepstream-6.3/deepstream-sample/config/config_infer_primary.txt",
    )

    pipeline.add(source)
    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(tracker)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(encoder)
    pipeline.add(h264parse)
    pipeline.add(qtmux)
    pipeline.add(sink)

    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(encoder)
    encoder.link(h264parse)
    h264parse.link(qtmux)
    qtmux.link(sink)

    source.connect("pad-added", on_pad_added, streammux)

    vehicle_tracker = VehicleTracker()
    osdsinkpad = nvosd.get_static_pad("sink")
    osdsinkpad.add_probe(
        Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, vehicle_tracker
    )

    loop = GLib.MainLoop()

    bus = pipeline.get_bus()
    bus.add_signal_watch()
    bus.connect("message", bus_call, loop)

    # Set state with timeout and verification
    print("Setting pipeline state to PLAYING...")
    ret = pipeline.set_state(Gst.State.PLAYING)
    if ret == Gst.StateChangeReturn.FAILURE:
        print("Unable to set the pipeline to playing state")
        bus = pipeline.get_bus()
        msg = bus.poll(Gst.MessageType.ERROR, 0)
        if msg:
            err, debug = msg.parse_error()
            print(f"Pipeline error: {err}")
            print(f"Debug info: {debug}")

        # Check individual element states
        for element in [
            source,
            streammux,
            pgie,
            tracker,
            nvvidconv,
            nvosd,
            encoder,
            h264parse,
            qtmux,
            sink,
        ]:
            state_return = element.get_state(0)
            print(
                f"Element {element.get_name()}:\n"
                f"  Current State: {get_state_name(state_return[1])}\n"
                f"  Pending State: {get_state_name(state_return[2])}\n"
                f"  Return Status: \033[91m{get_state_change_return(state_return[0])}\033[0m"
                if state_return[0] == Gst.StateChangeReturn.FAILURE
                else f"  Return Status: {get_state_change_return(state_return[0])}"
            )

        return -1
    elif ret == Gst.StateChangeReturn.ASYNC:
        print("Pipeline is changing state asynchronously...")
        ret = pipeline.get_state(Gst.CLOCK_TIME_NONE)
        if ret[0] == Gst.StateChangeReturn.SUCCESS:
            print("Pipeline successfully changed state to PLAYING")
        else:
            print(f"Pipeline failed to change state: {ret[0]}")
            return -1

    print("Entering main loop...")

    def signal_handler(sig, frame):
        print("Caught Ctrl+C, cleaning up...")
        loop.quit()
        pipeline.set_state(Gst.State.NULL)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    try:
        loop.run()
    except KeyboardInterrupt:
        print("Interrupted by user")
    finally:
        print("Cleaning up...")
        pipeline.set_state(Gst.State.NULL)
        loop.quit()


def on_pad_added(element, pad, data):
    caps = pad.get_current_caps()
    if not caps:
        return

    str_name = caps.get_structure(0).get_name()
    if str_name.startswith("video/"):
        sinkpad = data.get_request_pad("sink_0")
        if not pad.link(sinkpad) == Gst.PadLinkReturn.OK:
            print("Failed to link video pad")


def bus_call(bus, message, loop):
    t = message.type
    if t == Gst.MessageType.EOS:
        print("End-of-stream")
        loop.quit()
    elif t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        print(f"Error: {err}, {debug}")
        loop.quit()
    elif t == Gst.MessageType.STATE_CHANGED:
        old_state, new_state, pending_state = message.parse_state_changed()
        print(
            f"Pipeline state changed from {old_state.value_nick} to {new_state.value_nick}"
        )
        if pending_state != Gst.State.VOID_PENDING:
            print(f"Pending state: {pending_state.value_nick}")
    return True


if __name__ == "__main__":
    sys.exit(main())
