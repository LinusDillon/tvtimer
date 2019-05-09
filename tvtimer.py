import paho.mqtt.client as mqtt


class TvTimerDaemon(Daemon):

    def __init__(self, mqttServer, mqttPort, switchName):
        self.mqttServer = mqttServer
        self.mqttPort = mqttPort
        self.switchName = switchName
        self.sensorTopic = "tele/" + self.switchName + "/SENSOR"
        self.mqttClient = mqtt.Client()
        self.mqttClient.on_connect = self.mqttOnConnect
        self.mqttClient.on_message = self.mqttOnMessage
    
    def mqttOnConnect(client, userdata, flags, rc):
        print("Connected with result code " + str(rc))
        print("Subscribing to " + self.sensorTopic)
        client.subscribe(self.sensorTopic)

    def mqttOnMessage(client, userdata, msg):
        print(msg.topic + " " + str(msg.payload))

    def run(self):
        self.mqttClient.connect(self.mqttServer, self.mqttPort, 60)
        self.mqttClient.loop_start()
        while True:
            time.sleep(30)
        self.mqttClient.loop_stop()


if __name__ == "__main__":
    daemon = TvTimerDaemon()
    if len(sys.argv) == 2:
        if 'start' == sys.argv[1]:
            daemon.run()
        elif 'stop' == sys.argv[1]:
            print "Not implemented"
        elif 'restart' == sys.argv[1]:
            print "Not implemented"
        else:
            print "Unknown command"
            sys.exit(2)
        sys.exit(0)
    else:
        print "usage: %s start|stop|restart" % sys.argv[0]
        sys.exit(2)
