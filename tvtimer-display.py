import paho.mqtt.client as mqtt
import scrollphathd as sphd
from scrollphathd.fonts import font3x5

sphd.clear()
sphd.write_string("100:00", y=1, font=font3x5, brightness=0.5)
sphd.show()

# Connect/subscribe to tvtimer topic
# Write remaining time to display (MM:SS)
# Write TV power on/off state to display
