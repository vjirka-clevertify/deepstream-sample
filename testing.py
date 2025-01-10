#!/usr/bin/env python3

import sys
import time
import math
import gi
import pyds
import numpy as np
from collections import defaultdict

gi.require_version('Gst', '1.0')
from gi.repository import GObject, Gst

class VehicleTracker:
    def __init__(self):
        self.vehicles = defaultdict(list)
        self.speeds = defaultdict(list)
        self.frame_rate = 30.0
        self.real_world_width = 15.0
        self.pixels_per_meter = None

    def calculate_speed(self, positions, time_diff):
        if len(positions) < 2:
            return None
        
        # Calculate distance in pixels
        pixel_distance = math.sqrt(
            (positions[-1][1] - positions[0][1])**2 + 
            (positions[-1][2] - positions[0][2])**2
        )
        
        # Convert to real-world distance (meters)
        if self.pixels_per_meter is None:
            self.pixels_per_meter = 1920 / self.real_world_width
            
        distance = pixel_distance / self.pixels_per_meter
        
        # Calculate speed (m/s)
        speed = distance / time_diff
        
        # Convert to km/h
        return speed * 3.6

    def update_vehicle(self, track_id, bbox, frame_num):
        current_time = frame_num / self.frame_rate
        center_x = (bbox.left + bbox.width/2)
        center_y = (bbox.top + bbox.height/2)
        
        self.vehicles[track_id].append((current_time, center_x, center_y))
        
        # Keep only last 15 frames of history
        if len(self.vehicles[track_id]) > 15:
            self.vehicles[track_id].pop(0)
            
        # Calculate speed if we have enough positions
        if len(self.vehicles[track_id]) >= 2:
            positions = self.vehicles[track_id]
            time_diff = positions[-1][0] - positions[0][0]
            
            if time_diff > 0:
                speed = self.calculate_speed(positions, time_diff)
                if speed is not None and speed < 200:  # Filter out unrealistic speeds
                    self.speeds[track_id].append(speed)
                    
                    # Keep only last 5 speed measurements
                    if len(self.speeds[track_id]) > 5:
                        self.speeds[track_id].pop(0)

    def get_average_speed(self, track_id):
        if track_id in self.speeds and len(self.speeds[track_id]) > 0:
            return np.mean(self.speeds[track_id])
        return None

    def cleanup_old_tracks(self, current_frame):
        current_time = current_frame / self.frame_rate
        old_tracks = []
        
        for track_id, positions in self.vehicles.items():
            if current_time - positions[-1][0] > 2.0:  # Remove after 2 seconds
                old_tracks.append(track_id)
                
        for track_id in old_tracks:
            if track_id in self.speeds and len(self.speeds[track_id]) > 0:
                avg_speed = np.mean(self.speeds[track_id])
                print(f"Vehicle {track_id} average speed: {avg_speed:.2f} km/h")
            del self.vehicles[track_id]
            if track_id in self.speeds:
                del self.speeds[track_id]

# Global vehicle tracker instance
vehicle_tracker = VehicleTracker()
frame_count = 0

def osd_sink_pad_buffer_probe(pad, info, u_data):
    global vehicle_tracker, frame_count
    frame_count += 1
    
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    l_frame = batch_meta.frame_meta_list
    
    while l_frame:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        l_obj = frame_meta.obj_meta_list
        
        while l_obj:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            
            # Only track vehicles (class 0 in trafficcamnet)
            if obj_meta.class_id == 0:  # vehicle class
                vehicle_tracker.update_vehicle(
                    obj_meta.object_id, 
                    obj_meta.rect_params, 
                    frame_meta.frame_num
                )
            
            try:
                # Display speed on screen
                speed = vehicle_tracker.get_average_speed(obj_meta.object_id)
                if speed is not None:
                    txt_params = obj_meta.text_params
                    txt_params.display_text = f"{speed:.1f} km/h"
                    txt_params.font_params.font_size = 12
            except Exception as e:
                print(f"Error updating display text: {e}")
            
            l_obj = l_obj.next
            
        # Cleanup old tracks
        vehicle_tracker.cleanup_old_tracks(frame_meta.frame_num)
        l_frame = l_frame.next
        
    return Gst.PadProbeReturn.OK

def main(args):
    # Initialize GStreamer
    GObject.threads_init()
    Gst.init(None)

    # Create Pipeline
    pipeline = Gst.Pipeline()
    if not pipeline:
        sys.stderr.write(" Unable to create Pipeline\n")
        return -1

    # Create elements
    source = Gst.ElementFactory.make("filesrc", "file-source")
    demux = Gst.ElementFactory.make("qtdemux", "demuxer")  # For MP4 files
    decoder = Gst.ElementFactory.make("nvv4l2decoder", "nvv4l2-decoder")
    streammux = Gst.ElementFactory.make("nvstreammux", "stream-muxer")
    pgie = Gst.ElementFactory.make("nvinfer", "primary-nvinference-engine")
    tracker = Gst.ElementFactory.make("nvtracker", "tracker")
    nvvidconv = Gst.ElementFactory.make("nvvideoconvert", "converter")
    nvosd = Gst.ElementFactory.make("nvdsosd", "onscreendisplay")
    sink = Gst.ElementFactory.make("nveglglessink", "nvvideo-renderer")

    if not (source and demux and decoder and streammux and pgie and 
            tracker and nvvidconv and nvosd and sink):
        sys.stderr.write(" One or more elements could not be created. Exiting.\n")
        return -1

    # Set element properties
    source.set_property('location', 'video.mp4')
    streammux.set_property('width', 1920)
    streammux.set_property('height', 1080)
    streammux.set_property('batch-size', 1)
    streammux.set_property('batched-push-timeout', 4000000)
    pgie.set_property('config-file-path', "config/source1_primary_detector.txt")

    # Add elements to Pipeline
    print("Adding elements to Pipeline")
    pipeline.add(source)
    pipeline.add(demux)
    pipeline.add(decoder)
    pipeline.add(streammux)
    pipeline.add(pgie)
    pipeline.add(tracker)
    pipeline.add(nvvidconv)
    pipeline.add(nvosd)
    pipeline.add(sink)

    # Link elements
    print("Linking elements in the Pipeline")
    source.link(demux)
    
    def demux_pad_added(demux, pad, decoder):
        if pad.get_name().startswith('video'):
            sinkpad = decoder.get_static_pad("sink")
            pad.link(sinkpad)

    demux.connect("pad-added", demux_pad_added, decoder)

    sinkpad = streammux.get_request_pad("sink_0")
    srcpad = decoder.get_static_pad("src")
    srcpad.link(sinkpad)

    streammux.link(pgie)
    pgie.link(tracker)
    tracker.link(nvvidconv)
    nvvidconv.link(nvosd)
    nvosd.link(sink)

    # Add probe to get metadata
    osdsinkpad = nvosd.get_static_pad("sink")
    if not osdsinkpad:
        sys.stderr.write(" Unable to get sink pad of nvosd\n")
        return -1

    osdsinkpad.add_probe(Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0)

    # Start playing
    print("Starting pipeline")
    pipeline.set_state(Gst.State.PLAYING)

    # Create an event loop
    loop = GObject.MainLoop()

    try:
        loop.run()
    except KeyboardInterrupt:
        pass

    # Cleanup
    pipeline.set_state(Gst.State.NULL)

if __name__ == '__main__':
    sys.exit(main(sys.argv))