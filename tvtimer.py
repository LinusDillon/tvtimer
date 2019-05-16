import paho.mqtt.client as mqtt
import time
import datetime
import json
import logging
from logging.handlers import TimedRotatingFileHandler
from service import Service


class TvTimerDaemon(Service):

    def __init__(self, mqttServer, mqttPort, switchName, powerThreshold, weekdayLimit, weekendLimit, carryOverLimit):
        super(TvTimerDaemon, self).__init__("tvtimer", pid_dir='/tmp')
        self.logger.addHandler(TimedRotatingFileHandler(filename="/tmp/tvtimer.log", when='D', backupCount=7))
        self.logger.setLevel(logging.INFO)

        self.mqttServer = mqttServer
        self.mqttPort = mqttPort
        self.switchName = switchName
        self.powerThreshold = powerThreshold
        self.sensorTopic = "tele/" + self.switchName + "/SENSOR"
        self.switchTopic = "cmnd/" + self.switchName + "/Power"
        self.lastTvPowerOnState = False
        self.tvPowerOnTime = time.time()
        self.tvPowerOffTime = time.time()
        self.totalOnTimeToday = 0
        self.totalOnTimeTodayWhenPoweredOn = 0
        self.mqttClient = None
        self.weekdayLimit = weekdayLimit
        self.weekendLimit = weekendLimit
        self.carryOverLimit = carryOverLimit
        self.limitCarriedOver = 0
        self.effectiveOverride = ""
        self.startup = True

    def mqttOnConnect(self, client, userdata, flags, rc):
        self.logger.info("Connected with result code " + str(rc))
        self.logger.info("Subscribing to " + self.sensorTopic)
        client.subscribe([(self.sensorTopic, 0), ("tvtimer", 0), ("tvtimer-override", 0)])

    def mqttOnMessage(self, client, userdata, msg):
        self.logger.info(msg.topic + " " + str(msg.payload))
        if msg.topic == self.sensorTopic:
            # Extract the values we are interested in
            jsonPayload = str(msg.payload.decode("utf-8", "ignore"))
            objectPayload = json.loads(jsonPayload)
            power = objectPayload["ENERGY"]["Power"]
            self.logger.info("TV power use is " + str(power))
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
                self.logger.info("Received msg from tvtimer topic during startup")
                jsonPayload = str(msg.payload.decode("utf-8", "ignore"))
                objectPayload = json.loads(jsonPayload)
                if objectPayload['Date'] == self.calculateEffectiveDate():
                    # Apply initial state
                    self.limitCarriedOver = objectPayload['LimitCarriedOver']
                    self.totalOnTimeToday = objectPayload['TimeOnToday']
                    self.startup = False
        elif msg.topic == "tvtimer-override":
            overrideString = str(msg.payload.decode("utf-8", "ignore"))
            if overrideString == "just10moreminutes" and self.effectiveOverride != "10 More Minutes":
                self.effectiveLimit += 60 * 10
                self.effectiveOverride = "10 More Minutes"

    def calculateEffectiveDate(self):
        today = datetime.datetime.now() - datetime.timedelta(hours=4)
        return today.date().isoformat()

    def calculateEffectiveLimit(self):
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
        self.date = self.calculateEffectiveDate()
        self.effectiveLimit = self.calculateEffectiveLimit()
        self.effectiveOverride = ""

    def updateSwitchState(self, enable):
        if enable:
            self.mqttClient.publish(self.switchTopic, "ON")
        else:
            self.mqttClient.publish(self.switchTopic, "OFF")

    def run(self):
        self.mqttClient = mqtt.Client()
        self.mqttClient.on_connect = self.mqttOnConnect
        self.mqttClient.on_message = self.mqttOnMessage
        self.mqttClient.connect(self.mqttServer, self.mqttPort, 60)
        self.mqttClient.loop_start()

        # Wait a short time after starting the MQTT client to connect and try and receive the last published state
        time.sleep(2)
        self.date = self.calculateEffectiveDate()
        self.effectiveLimit = self.calculateEffectiveLimit()
        loopDivisor = 0
        publishPayload = {}
        self.startup = False
        while not self.got_sigterm():
            # If TV is on, update the total on time
            if self.lastTvPowerOnState:
                elapsedOnTime = time.time() - self.tvPowerOnTime
                self.totalOnTimeToday = self.totalOnTimeTodayWhenPoweredOn + elapsedOnTime
            if (loopDivisor % 60) == 0:
                self.logger.info("TV on time today is " + str(self.totalOnTimeToday))

            # Reset for the next day of the date has changed
            if self.calculateEffectiveDate() != self.date:
                self.resetForNextDay()

            remainingToday = self.limitRemainingForToday()
            tvEnable = (remainingToday > 0)
            self.updateSwitchState(tvEnable)

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
            publishPayload['Override'] = self.effectiveOverride
            publishPayload['Date'] = self.date
            self.mqttClient.publish("tvtimer", json.dumps(publishPayload), retain=True)

            loopDivisor += 1
            time.sleep(1)
        self.mqttClient.loop_stop()


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        sys.exit('Syntax: %s COMMAND' % sys.argv[0])

    cmd = sys.argv[1].lower()
    service = TvTimerDaemon("zen", 1883, "sonoff-tv", 20, 80 * 60, 100 * 60, 15 * 60)

    if cmd == 'start':
        service.start()
    elif cmd == 'stop':
        service.stop()
    elif cmd == 'status':
        if service.is_running():
            print "Service is running."
        else:
            print "Service is not running."
    else:
        sys.exit('Unknown command "%s".' % cmd)
