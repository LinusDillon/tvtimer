import paho.mqtt.client as mqtt
import time
import datetime
import json


class TvTimerDaemon():

    def __init__(self, mqttServer, mqttPort, switchName, powerThreshold, weekdayLimit, weekendLimit, carryOverLimit):
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
        self.weekdayLimit = weekdayLimit
        self.weekendLimit = weekendLimit
        self.carryOverLimit = carryOverLimit
        self.limitCarriedOver = 0
        self.startup = True

    def mqttOnConnect(self, client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        print("Subscribing to " + self.sensorTopic)
        client.subscribe([(self.sensorTopic, 0), ("tvtimer", 0)])

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
        elif msg.topic == "tvtimer":
            if self.startup:
                print("Received msg from tvtimer topic during startup")
                jsonPayload = str(msg.payload.decode("utf-8", "ignore"))
                objectPayload = json.loads(jsonPayload)
                if objectPayload['Date'] == self.effectiveDate():
                    # Apply initial state
                    self.limitCarriedOver = objectPayload['LimitCarriedOver']
                    self.totalOnTimeToday = objectPayload['TimeOnToday']
                    self.startup = False

    def effectiveDate(self):
        today = datetime.datetime.now() - datetime.timedelta(hours=4)
        return today.date().isoformat()

    def effectiveLimit(self):
        today = datetime.datetime.now() - datetime.timedelta(hours=4)
        dayOfWeek = today.weekday()
        if dayOfWeek < 5:
            return self.weekdayLimit
        else:
            return self.weekendLimit

    def limitRemainingForToday(self):
        remaining = (self.effectiveLimit + self.limitCarriedOver) - self.totalOnTimeToday
        if remaining < 0:
            remaining = 0
        return remaining

    def resetForNextDay(self):
        self.limitCarriedOver = self.limitRemainingForToday()
        if self.limitCarriedOver > self.carryOverLimit:
            self.limitCarriedOver = self.carryOverLimit
        self.date = self.effectiveDate()
        self.effectiveLimit = self.effectiveLimit()

    def run(self):
        self.mqttClient.connect(self.mqttServer, self.mqttPort, 60)
        self.mqttClient.loop_start()

        # Wait a short time after starting the MQTT client to connect and try and receive the last published state
        time.sleep(2)
        self.date = self.effectiveDate()
        self.effectiveLimit = self.effectiveLimit()
        loopDivisor = 0
        publishPayload = {}
        self.startup = False
        while True:
            # If TV is on, update the total on time
            if self.lastTvPowerOnState:
                elapsedOnTime = time.time() - self.tvPowerOnTime
                self.totalOnTimeToday = self.totalOnTimeTodayWhenPoweredOn + elapsedOnTime
            if (loopDivisor % 60) == 0:
                print("TV on time today is " + str(self.totalOnTimeToday))

            # Reset for the next day of the date has changed
            if self.effectiveDate() != self.date:
                self.resetForNextDay()

            remainingToday = self.limitRemainingForToday()
            tvEnable = (remainingToday > 0)

            publishPayload['TimeOnToday'] = self.totalOnTimeToday
            publishPayload['TvPowerState'] = self.lastTvPowerOnState
            publishPayload['WeekdayLimit'] = self.weekdayLimit
            publishPayload['WeekendLimit'] = self.weekendLimit
            publishPayload['CarryOverLimit'] = self.carryOverLimit
            publishPayload['TodaysLimit'] = self.effectiveLimit + self.limitCarriedOver
            publishPayload['LimitCarriedOver'] = self.limitCarriedOver
            publishPayload['EffectiveLimit'] = self.effectiveLimit
            publishPayload['RemainingToday'] = remainingToday
            publishPayload['TvEnableState'] = tvEnable
            publishPayload['Date'] = self.date
            self.mqttClient.publish("tvtimer", json.dumps(publishPayload), retain=True)

            loopDivisor += 1
            time.sleep(1)
        self.mqttClient.loop_stop()

# TODO
# Switch off TV if reached applied limits
# Read limit bypass codes from topic and apply
# Make a proper service with start/stop/restart


if __name__ == "__main__":
    daemon = TvTimerDaemon("zen", 1883, "sonoff-tv", 20, 80 * 60, 100 * 60, 15 * 60)
    daemon.run()
