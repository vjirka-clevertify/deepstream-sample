import configparser
import sys
from pykafka import KafkaClient
import gi
import logging

gi.require_version("Gst", "1.0")
from gi.repository import Gst, GObject

logging.basicConfig(level=logging.INFO)

# Read configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Kafka configuration
kafka_bootstrap_servers = config['KAFKA']['bootstrap_servers']
kafka_topic = config['KAFKA']['topic']

# Detection configuration
reference_point1_x = int(config['DETECTION']['reference_point1_x'])
reference_point1_y = int(config['DETECTION']['reference_point1_y'])
reference_point2_x = int(config['DETECTION']['reference_point2_x'])
reference_point2_y = int(config['DETECTION']['reference_point2_y'])
real_distance = float(config['DETECTION']['real_distance'])

# Kafka producer
def send_to_kafka(vehicle_data):
    try:
        client = KafkaClient(hosts=kafka_bootstrap_servers)
        topic = client.topics[kafka_topic.encode('utf-8')]
        with topic.get_producer() as producer:
            producer.produce(vehicle_data.encode("utf-8"))
    except Exception as e:
        logging.error(f"Error sending data to Kafka: {e}")

# Vehicle processing callback
def osd_sink_pad_buffer_probe(pad, info, u_data):
    gst_buffer = info.get_buffer()
    if not gst_buffer:
        return Gst.PadProbeReturn.OK

    # Parse vehicle data (mockup logic)
    vehicles = [
        {"id": 1, "speed": 45.2, "bbox": [50, 50, 100, 100]},
        {"id": 2, "speed": 60.1, "bbox": [150, 150, 200, 200]},
    ]

    for vehicle in vehicles:
        vehicle_data = f"Vehicle ID: {vehicle['id']}, Speed: {vehicle['speed']}, BBox: {vehicle['bbox']}"
        logging.info(vehicle_data)
        send_to_kafka(vehicle_data)

    return Gst.PadProbeReturn.OK

def main():
    Gst.init(None)

    # GStreamer pipeline
    pipeline = Gst.parse_launch(
        """
        filesrc location=video.mp4 ! decodebin ! nvstreammux name=mux batch-size=1 width=960 height=544 ! 
        nvinfer config-file-path=config_infer_primary_trafficcamnet.txt ! nvdsosd ! 
        videoconvert ! autovideosink
        """
    )

    osd_sink_pad = pipeline.get_by_name("nvdsosd").get_static_pad("sink")
    osd_sink_pad.add_probe(
        Gst.PadProbeType.BUFFER, osd_sink_pad_buffer_probe, 0
    )

    pipeline.set_state(Gst.State.PLAYING)

    try:
        loop = GObject.MainLoop()
        loop.run()
    except Exception as e:
        logging.error(f"Main loop error: {e}")

    pipeline.set_state(Gst.State.NULL)

if __name__ == "__main__":
    sys.exit(main())