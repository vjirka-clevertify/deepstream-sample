#!/bin/bash
apt-get update && apt-get install -y sudo
sudo apt install -y python3-pip
sudo apt-get install -y nano
sudo apt-get install -y libcairo2-dev
sudo apt install -y libgirepository1.0-dev
sudo apt install -y wormhole
sudo apt install -y python3-gst-1.0
sudo apt install -y gstreamer1.0-plugins-base
sudo apt install -y gstreamer1.0-plugins-good
sudo apt install -y gstreamer1.0-plugins-bad
sudo apt install -y gstreamer1.0-plugins-ugly
sudo apt install -y gstreamer1.0-libav
sudo apt install -y libavcodec58
sudo apt install -y libmpg123-0
sudo apt install -y libmpeg2-4
sudo apt install -y libopenmpt0
wget https://github.com/NVIDIA-AI-IOT/deepstream_python_apps/releases/download/v1.1.8/pyds-1.1.8-py3-none-linux_x86_64.whl
pip install pyds-1.1.8-py3-none-linux_x86_64.whl
pip install -r requirements.txt