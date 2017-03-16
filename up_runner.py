import json
import os
import subprocess
import time
from threading import Thread

import yaml
from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint
from twisted.internet.protocol import Protocol, Factory
from up.utils.up_logger import UpLogger


class UpRunner:
    PORT = 3002
    TERM_TIMEOUT_S = 10

    def __init__(self):
        self.__logger = UpLogger.get_logger()
        self.logger.info("Initializing UpRunner")
        self.__path_to_up = None
        self.__up_proc = None
        self.__application_root = None
        self.__script_path = None
        self.__read_config()

        spawn_endpoint = TCP4ServerEndpoint(reactor, self.PORT)
        self.__protocol = UpSpawnProtocol(self)
        spawn_endpoint.listen(UpSpawnProtocolFactory(self.__protocol))


    def run(self):
        self.logger.info("Up Runner started")
        reactor.run()

    def stop(self):
        self.logger.info("Up Runner stopped")

    def on_spawn_request(self):
        if self.up_proc:
            self.logger.info("Up already running, no need to spawn")
            self.__protocol.transport.write(self.__create_spawn_message('Raspilot already running', True, None))
        else:
            self.logger.info("Spawning new Up Application")
            os.chdir(self.__application_root)
            self.logger.debug("Moving to %s" % os.getcwd())
            Thread(target=self.__run_up, args=(self.__script_path,), name='SCRIPT_WORKER_THREAD').start()
            time.sleep(2)
            self.__protocol.transport.write(self.__create_spawn_message('Raspilot spawned', True, None))

    def __read_config(self):
        with open('./config/runner.yml') as f:
            config = yaml.load(f)
            self.__application_root = config.get('application root', None)
            self.__script_path = config.get('script path', None)

    def __run_up(self, script_path):
        self.__up_proc = subprocess.Popen(['python', script_path], stderr=subprocess.DEVNULL)
        self.logger.info("Up Application running with PID %s" % self.up_proc.pid)

    def __create_spawn_message(self, message, spawned, error):
        message = {'message': message, 'spawned': spawned, 'error': error,
                'myAddress': self.__protocol.transport.client[0]}
        json_message = json.dumps(message)
        json_message += '\n'
        return bytes(json_message.encode('utf-8'))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.up_proc:
            pid = self.up_proc.pid
            self.up_proc.terminate()
            try:
                self.up_proc.wait(self.TERM_TIMEOUT_S)
                self.logger.info("Up Application with PID %s terminated" % pid)
            except subprocess.TimeoutExpired:
                self.logger.error('Up Application does not respond and will be killed')
                self.up_proc.kill()

    @property
    def logger(self):
        return self.__logger

    @property
    def up_proc(self):
        return self.__up_proc


class UpSpawnProtocol(Protocol):
    """
    Simple protocol, which calls the callback method on_spawn_request upon receiving data. Used when spawning Raspilot.
    """

    def __init__(self, callbacks):
        self.__callbacks = callbacks

    def dataReceived(self, data):
        self.__callbacks.on_spawn_request()


class UpSpawnProtocolFactory(Factory):
    def __init__(self, protocol):
        self.__protocol = protocol

    def buildProtocol(self, addr):
        return self.__protocol


if __name__ == '__main__':
    runner = UpRunner()
    try:
        with runner:
            runner.run()
    except KeyboardInterrupt:
        pass
    finally:
        runner.stop()
