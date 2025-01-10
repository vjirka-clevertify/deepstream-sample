import gi
import sys
import signal
from gi.repository import Gst, GLib

gi.require_version("Gst", "1.0")
from utils import calculate_vehicle_speed

# Global variables for pipeline and loop
pipeline = None
loop = None


def osd_sink_pad_buffer_probe(pad, info, u_data):
    """
    Probe function to process metadata from inference results.
    """
    batch_meta = Gst.NvDsBatchMeta.cast(info.get_buffer().meta)
    l_frame = batch_meta.frame_meta_list

    while l_frame is not None:
        frame_meta = l_frame.data
        l_obj = frame_meta.obj_meta_list

        while l_obj is not None:
            obj_meta = l_obj.data

            # Extract object data
            vehicle_id = obj_meta.object_id
            position = (obj_meta.tracker_bbox_info.org_bbox_coords.left, obj_meta.tracker_bbox_info.org_bbox_coords.top)
            timestamp = frame_meta.ntp_timestamp

            # Calculate vehicle speed
            speed = calculate_vehicle_speed(vehicle_id, position, timestamp)
            print(f"Vehicle ID: {vehicle_id}, Speed: {speed:.2f} km/h")

            l_obj = l_obj.next

        l_frame = l_frame.next

    return Gst.PadProbeReturn.OK


def signal_handler(sig, frame):
    """
    Graceful shutdown on signal interrupt (Ctrl+C).
    """
    global pipeline, loop
    print("Interrupt received, stopping pipeline...")
    if pipeline:
        pipeline.set_state(Gst.State.NULL)
    if loop:
        loop.quit()


def main():
    global pipeline, loop

    # Initialize GStreamer
    Gst.init(None)

    # Load pipeline without Kafka
    pipeline = Gst.parse_launch(
        "uridecodebin uri=file://path_to_video.mp4 ! "
        "nvvideoconvert ! nvinfer config-file-path=./config/source1_primary_detector.txt ! "
        "nvtracker ! fakesink"
    )

    if not pipeline:
        print("Failed to create pipeline.")
        sys.exit(1)

    # Add OSD probe to process metadata
    osd_sink_pad = pipeline.get_by_name("nvtracker").get_static_pad("src")
    if osd_sink_pad:
        osd_sink_pad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # Set up the main loop
    loop = GLib.MainLoop()

    # Handle interrupt signals for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)

    # Start the pipeline
    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop.run()
    except Exception as e:
        print(f"Error during execution: {e}")
    finally:
        # Cleanup
        pipeline.set_state(Gst.State.NULL)


if __name__ == "__main__":
    main()
