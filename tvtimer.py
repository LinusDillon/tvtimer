import paho.mqtt.client as mqtt
import time
import datetime
import json


class TvTimerDaemon():

    def __init__(self, mqttServer, mqttPort, switchName, powerThreshold, dailyLimit, weeklyLimit, carryOverLimit):
        self.mqttServer = mqttServer
        self.mqttPort = mqttPort
        self.switchName = switchName
        self.powerThreshold = powerThreshold
        self.sensorTopic = "tele/" + self.switchName + "/SENSOR"
        self.lastTvPowerOnState = False
        self.tvPowerOnTime = time.time()
        self.tvPowerOffTime = time.time()
        self.totalOnTimeToday = 0
        self.totalOnTimeTodayWhenPoweredOn = 0
        self.mqttClient = mqtt.Client()
        self.mqttClient.on_connect = self.mqttOnConnect
        self.mqttClient.on_message = self.mqttOnMessage
        self.dailyLimit = dailyLimit
        self.weeklyLimit = weeklyLimit
        self.carryOverLimit = carryOverLimit

    def mqttOnConnect(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        print("Subscribing to " + self.sensorTopic)
        client.subscribe(self.sensorTopic)

    def mqttOnMessage(self, client, userdata, msg):
        print(msg.topic + " " + str(msg.payload))
        if msg.topic == self.sensorTopic:
            # Extract the values we are interested in
            jsonPayload = str(msg.payload.decode("utf-8", "ignore"))
            objectPayload = json.loads(jsonPayload)
            power = objectPayload["ENERGY"]["Power"]
            print("TV power use is " + str(power))
            tvPowerOnState = (power > self.powerThreshold)
            if tvPowerOnState and not self.lastTvPowerOnState:
                # TV has been turned on
                self.tvPowerOnTime = time.time()
                self.totalOnTimeTodayWhenPoweredOn = self.totalOnTimeToday
            elif not tvPowerOnState and self.lastTvPowerOnState:
                # TV has been turned off
                self.tvPowerOffTime = time.time()
            self.lastTvPowerOnState = tvPowerOnState

    def effectiveDate(self):
        today = datetime.datetime.now() - datetime.timedelta(hours=4)
        return today.date().isoformat()

    def run(self):
        self.mqttClient.connect(self.mqttServer, self.mqttPort, 60)
        self.mqttClient.loop_start()
        self.date = self.effectiveDate()
        loopDivisor = 0
        publishPayload = {}
        while True:
            # If TV is on, update the total on time
            if self.lastTvPowerOnState:
                elapsedOnTime = time.time() - self.tvPowerOnTime
                self.totalOnTimeToday = self.totalOnTimeTodayWhenPoweredOn + elapsedOnTime
            if (loopDivisor % 60) == 0:
                print("TV on time today is " + str(self.totalOnTimeToday))

            publishPayload['TimeOnToday'] = self.totalOnTimeToday
            publishPayload['TvPowerState'] = self.lastTvPowerOnState
            publishPayload['DailyLimit'] = self.dailyLimit
            publishPayload['WeeklyLimit'] = self.weeklyLimit
            publishPayload['CarryOverLimit'] = self.carryOverLimit
            publishPayload['Date'] = self.date
            self.mqttClient.publish("tvtimer", json.dumps(publishPayload), retain=True)

            loopDivisor += 1
            time.sleep(1)
        self.mqttClient.loop_stop()

# TODO
# Push total on time today to topic
# Push day to topic
# Read total time today + day from topic and apply to self.totalOnTimeToday if for same day
# Reset total time today/day at configured time each day
# Calculate week+total time this week/push to topic/read from topic on startup if same week
# Read default and applied limits from topic
# Switch off TV if reached applied limits
# Read limit bypass codes from topic and apply
# Reset applied limits to default limits each day
# Make a proper service with start/stop/restart


if __name__ == "__main__":
    daemon = TvTimerDaemon("zen", 1883, "sonoff-tv", 20, 80, 500, 15)
    daemon.run()
