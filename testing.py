#!/usr/bin/env python3

import sys
import math
import gi
import pyds
import numpy as np
from collections import defaultdict

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
                display_text = (
                    f"ID: {obj_meta.object_id} Speed: {speed:.1f} km/h"
                )
                py_nvosd_text_params = pyds.nvds_add_display_meta_to_frame(
                    frame_meta,
                    display_text,
                    int(obj_meta.rect_params.left),
                    int(obj_meta.rect_params.top - 10),
                )
            l_obj = l_obj.next
        l_frame = l_frame.next

    return Gst.PadProbeReturn.OK


def main():
    Gst.init(None)
    pipeline = Gst.Pipeline()

    # Create elements
    source = Gst.ElementFactory.make("uridecodebin", "uri-decode-bin")
    streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-inference")
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    sink = Gst.ElementFactory.make("nveglglessink", "egl-output")

    if not all([source, streammux, pgie, tracker, nvvidconv, nvosd, sink]):
        sys.stderr.write(
            " One or more elements could not be created. Exiting.\n"
        )
        return -1

    source.set_property(
        "uri",
        "file:///opt/nvidia/deepstream/deepstream-6.3/deepstream_test1.mp4",
    )
    streammux.set_property("width", 1920)
    streammux.set_property("height", 1080)
    streammux.set_property("batch-size", 1)
    streammux.set_property("live-source", 0)
    streammux.set_property("nvbuf-memory-type", 0)
    streammux.set_property("frame-duration", 33333333)
    pgie.set_property("config-file-path", "config/config_infer_primary.txt")
    tracker.set_property("ll-config-file", "config/tracker_config.txt")

    pipeline.add(source)
    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(tracker)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(sink)

    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(sink)

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
            sink,
        ]:
            state_return = element.get_state(0)
            print(
                f"Element {element.get_name()}: State={state_return[1]}, "
                f"Pending={state_return[2]}, Return={state_return[0]}"
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
    try:
        loop.run()
    except KeyboardInterrupt:
        pass
    print("Exiting main loop...")
    pipeline.set_state(Gst.State.NULL)
    print("Pipeline stopped.")


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


def on_pad_added(element, pad, data):
    caps = pad.get_current_caps()
    if not caps:
        return

    str_name = caps.get_structure(0).get_name()
    if str_name.startswith("video/"):
        sinkpad = data.get_request_pad("sink_0")
        if not pad.link(sinkpad) == Gst.PadLinkReturn.OK:
            print("Failed to link video pad")


if __name__ == "__main__":
    sys.exit(main())
