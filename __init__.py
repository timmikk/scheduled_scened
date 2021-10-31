from datetime import date, datetime, time, timedelta, timezone
from typing import List

#from pyscript.apps.scheduled_scenes.TransitionConf import TransitionConf

from . import TransitionConf

CONF_NAME = "name"
CONF_LIGHTS = "lights"
CONF_SCHEDULE = "schedule"
CONF_TRANSITION_TIME = "transition_time"
CONF_TRANSITION_INTERVAL = "transition_interval"
CONF_BRIGHTNESS = "brightness"
CONF_COLOR_TEMP = "temp"
CONF_TIME = "time"
CONF_DISABLE_WHEN_LIGHTS_OFF = "disable_when_lights_off"
CONF_TRANSITION_TIME_ON_LIGHT_TURN_ON = "transition_time_light_on_trigger"

DEFAULT_TRANSITION_TIME = 30
DEFAULT_INTERVAL = 30
DEFAULT_DISABLE_WHEN_LIGHTS_OFF = True

class Programs:
    conf = None

    programs = []

    
    
    def __init__(self, conf):
        self.conf = conf

        for p in conf:
            self.programs.append(Program(p))

    def transitionAll(self):
        for p in self.programs:
            p.transitionAll()





class Program:
    conf = None

    lightTriggers = []

    services = []

    allowTurnLightsOn = False

    enabled = True

    periodicTrigger = None

    currentTransition = None

    enableTime = None

    enableTrigger = None

    def __init__(self, conf):
        self.conf = conf

        log.debug(f"Initializing Program: {self.name()}")
        
        self.getCurrentTransition()
        self.initTriggers()
        self.initServices()

    def getCurrentTransition(self):
        if self.currentTransition is None:
            self.currentTransition = self.findTransition()
            return self.currentTransition
        elif self.currentTransition.isOngoing():
            return self.currentTransition
        elif self.currentTransition.next() is not None and self.currentTransition.next().isOngoing():
            self.currentTransition = self.currentTransition.next()
            return self.currentTransition
        else:
            self.currentTransition = None
            return self.currentTransition
            

    def findTransition(self):
        #Get previous days last transition as it is probably first transition today
        t = self.getTransition(index = len(self.getScheduleConf())-1, day = date.today()-timedelta(days=1))
        now = datetime.now()

        for i in range(len(self.getScheduleConf()*2)):
            if t.isOngoing():
                self.currentTransition = t
                return t
            if t.startDateTime() > now:
                break
            t = t.next()
        log.warning(f"No transition was found") 
        return None

    def getTransition(self, index=0, day = date.today()):
        return TransitionConf(conf=self.getScheduleConf(), parent=self, index=index, day=day)
        
    def initTriggers(self):
        for l in self.lights():
            self.initLightTrigger(l)
        if self.allowTransition:
            self.initPeriodicTrigger()
        else:
            self.periodicTrigger = None
            log.debug(f"Periodig trigger disabled as transitions not allowed")


    def initPeriodicTrigger(self):
        interval = self.transitionInterval()

        @time_trigger(f"period(now, {interval})")
        def periodicTrigger(value=None):
            self.transition()

        self.periodicTrigger = periodicTrigger
        log.debug(f"Periodig trigger created with interval of {interval}s")


    def initLightTrigger(self, entityId):
        log.debug(f"Init light trigger for: {entityId}")
        @state_trigger(f"{entityId}")
        def lightTrigger(value=None):
            log.warning(f"Light Trigger fired: -{value}-")
            if value == 'on':
                log.warning("Value is on")
                self.transition(transitionTimeOverride = self.transitionTime_lightOnTrigger())
                
        
        self.lightTriggers.append(lightTrigger)

    def initServices(self):
        @service(f"scheduled_scenes_{self.name()}.turn_on")
        def turn_on(transition = 1):
            self.turnOn(transition_time = transition)
        @service(f"scheduled_scenes_{self.name()}.turn_off")
        def turn_off(transition = 1):
            self.turnOff(transition_time = transition)
        @service(f"scheduled_scenes_{self.name()}.enable")
        def enable():
            self.setEnabled(enabled = True)
        @service(f"scheduled_scenes_{self.name()}.disable")
        def disable(duration):
            self.setEnabled(enabled = False, duration=duration)

        self.services.append(turn_on)
        self.services.append(turn_off)
        self.services.append(enable)
        self.services.append(disable)


    def isAnylightOn(self):
        for l in self.lights():
            if state.get(l) is 'on':
                return True
        return False
    
    def allowTransition(self):
        allow = self.enabled
        log.debug(f"Allow transition = {allow}: enabled={self.enabled} AND (allowTurnLightsOn={self.allowTurnLightsOn} OR self.isAnylightOn()={self.isAnylightOn()})")
        
        return allow

    def transition(self, transitionTimeOverride = None, allowTurnLightsOn = None):
        log.debug(f"Program transition triggered with transitionTimeOverride={transitionTimeOverride}")
        if self.allowTransition and self.getCurrentTransition() is not None:
            self.getCurrentTransition().transition(transitionTimeOverride = transitionTimeOverride, allowTurnLightsOn = allowTurnLightsOn)

    def turnOn(self, transition_time = 1):
        self.transition(transitionTimeOverride = transition_time, allowTurnLightsOn = True)

    def turnOff(self, transition_time = 1):
        for l in self.lights():
            light.turn_off(entity_id=l, transition = transition_time)

    def setEnabled(self, enabled, duration=240):
        if not enabled:
            if duration == 0:
                self.enableTime = None
                self.enableTrigger = None
                log.info(f"Program [{self.name()}] DISABLED until manually re-enabled.")
            else:
                self.enableTime = datetime.now() + timedelta(minutes = duration)
                @time_trigger(f"once({self.enableTime})")
                def enableTrigger(value=None):
                    log.debug(f"Enable trigger fired for [{self.name()}].")
                    self.setEnabled(True)
                self.enableTrigger = enableTrigger
                log.info(f"Program [{self.name()}] DISABLED for {duration} minutes. Will be re-enabled at {self.enableTime}.")
        else:
            self.enableTime = None
            self.enableTrigger = None
            log.info(f"Program [{self.name()}] ENABLED.")
        self.enabled = enabled

    def getScheduleConf(self):
        if CONF_SCHEDULE in self.conf:
            return self.conf[CONF_SCHEDULE]
        else:
            return []

    def lights(self):
        if CONF_LIGHTS in self.conf:
            return self.conf[CONF_LIGHTS]

    def transitionTime(self):
        if CONF_TRANSITION_TIME in self.conf:
            return self.conf[CONF_TRANSITION_TIME]
        else:
            return 120

    def transitionTime_lightOnTrigger(self):
        if CONF_TRANSITION_TIME_ON_LIGHT_TURN_ON in self.conf:
            return self.conf[CONF_TRANSITION_TIME_ON_LIGHT_TURN_ON]
        else:
            return 1

    
    
    def transitionInterval(self):
        if CONF_TRANSITION_INTERVAL in self.conf:
            return self.conf[CONF_TRANSITION_INTERVAL]
        else:
            return 120

    def name(self):
        if CONF_NAME in self.conf:
            return self.conf[CONF_NAME]
        else:
            return ''



class TransitionConf:
    index = None
    day = None
    conf = []
    _next = None
    parent = None

    lastTransitionTime = None
    
    def __init__(self, conf, parent, index, day=date.today()):
        self.conf = conf
        self.parent = parent
        self.index = index
        self.day = day


    def findNext(self, transition):
        index = transition.index+1
        day = transition.day

        if index >= len(transition.conf):
            index = 0
            day = transition.day + timedelta(days=1)

        nextT = TransitionConf(conf=transition.conf, parent=transition.parent, index=index, day = day)
        if nextT.startDateTime() <= transition.startDateTime():
            return self.findNext(nextT)

        return nextT
        

    def next(self):
        if self._next is  None:
            self._next = self.findNext(self)
        
        return self._next



    def isOngoing(self):
        now = datetime.now()
        result = self.startDateTime() <= now and self.endDateTime() > now
        return result

    def strTimeToTime(self, timeString):
        if timeString == None:
            return None
        return time.fromisoformat(timeString)

    def clockTimeToDatetime(self, timeString, day = datetime.today()):
        if timeString == None:
            return None

        # make a datetime object with today's date
        dt = datetime.combine(day, datetime.strptime(timeString, '%H:%M').time())
        return dt


    def getTransitionConf(self):
        return self.conf[self.index]

    def startTime(self):
        if CONF_TIME in self.getTransitionConf():
            return self.getTransitionConf()[CONF_TIME]
        else:
            log.warning(f"time not defined in transition") #TODO Täydennä virhe
            return None

    def endTime(self):
        if next != None:
            return self.next().startTime()
        else:
            return None

    def startDateTime(self):
        return datetime.combine(self.day, self.strTimeToTime(self.startTime()))
    
    def endDateTime(self):
        if self.next() != None:
            return self.next().startDateTime()
        else:
            return None

    def brightnessStart(self):
        if CONF_BRIGHTNESS in self.getTransitionConf():
            return self.getTransitionConf()[CONF_BRIGHTNESS]
        else:
            log.warning(f"brightness not defined in transition") #TODO Täydennä virhe
            return None
    
    def brightnessEnd(self):
        if next != None:
            return self.next().brightnessStart()
        else:
            return None
    
    def colorTempStart(self):
        if CONF_COLOR_TEMP in self.getTransitionConf():
            return self.getTransitionConf()[CONF_COLOR_TEMP]
        else:
            log.warning(f"temp not defined in transition") #TODO Täydennä virhe
            return None
    
    def colorTempEnd(self):
        if next != None:
            return self.next().colorTempStart()
        else:
            return None

    def transitionTime(self) -> int:
        return self.parent.transitionTime()
    
    def lights(self) -> List[str]:
        return self.parent.lights()

    def totalTransitionSeconds(self) -> int:
        log.debug(f"totalTransitionSeconds: {self.endDateTime()} - {self.startDateTime()}: {(self.endDateTime() - self.startDateTime()).total_seconds()}")
        seconds = (self.endDateTime() - self.startDateTime()).total_seconds()
        return seconds
    
    def secondsFromTransitionStart(self) -> int:
        seconds = (datetime.now() - self.startDateTime()).total_seconds()
        log.debug(f"secondsFromTransitionStart: {seconds} = ({datetime.now()} - {self.startDateTime()}).total_seconds()")
        return seconds

    def brightnessPerSec(self) -> float:
        return (self.brightnessEnd() - self.brightnessStart()) / self.totalTransitionSeconds()

    def colorTempPerSec(self) -> float:
        colorTempPerSec = (self.colorTempEnd() - self.colorTempStart()) / self.totalTransitionSeconds()
        log.debug(f"colorTempPerSec: {colorTempPerSec} = ({self.colorTempEnd()} - {self.colorTempStart()}) / {self.totalTransitionSeconds()}")
        return colorTempPerSec

    def isLightOn(self, light):
        return state.get(light) == 'on'

    def allowTurnLightsOn(self):
        return self.parent.allowTurnLightsOn

    def allowTransition(self):
        return self.parent.allowTransition()

    def transition(self, transitionTimeOverride = None, allowTurnLightsOn = None):
        if not self.allowTransition():
            log.debug(f"Transition [{self.index}]: {self.startTime()} - {self.endTime()} was ignored as transitions are not allowed: self.allowTransition()={self.allowTransition()}")
            return

        if allowTurnLightsOn == None:
            allowTurnLightsOn = self.allowTurnLightsOn()
        
        log.debug(f"Transitioning")

        now = datetime.now()
        self.lastTransitionTime = now

        secondsFromTranstionStart = self.secondsFromTransitionStart()
        transitionSeconds = transitionTimeOverride if transitionTimeOverride != None else min((now - self.startDateTime()).total_seconds(), self.transitionTime())
        brightness = round(self.brightnessStart() + self.brightnessPerSec() * secondsFromTranstionStart)
        colorTemp = round(self.colorTempStart() + self.colorTempPerSec() * secondsFromTranstionStart)

        log.debug(f"Transition calculation: transitionSeconds={transitionSeconds}, ")
        log.debug(f"brightness: {brightness} = round({self.brightnessStart()} + {self.brightnessPerSec()} * {secondsFromTranstionStart})")
        log.debug(f"colorTemp {colorTemp} = round({self.colorTempStart()} + {self.colorTempPerSec()} * {secondsFromTranstionStart})")

        if self.brightnessPerSec() > 0:
            if brightness > self.brightnessEnd():
                brightness = self.brightnessEnd()
        else:
            if brightness < self.brightnessEnd():
                brightness = self.brightnessEnd()
        
        if self.colorTempPerSec() > 0:
            if colorTemp > self.colorTempEnd():
                colorTemp = self.colorTempEnd()
        else:
            if colorTemp < self.colorTempEnd():
                colorTemp = self.colorTempEnd()

        for l in self.lights():
            log.info(f"Transitioning Light: {l}, is on: {self.isLightOn(l)}")
            if(allowTurnLightsOn or self.isLightOn(l)):
                log.info(f"Transition: light = {l}, seconds = {transitionSeconds}, brightness = {brightness}, colorTemp = {colorTemp}")
                light.turn_on(entity_id=l, brightness_pct = brightness, kelvin = colorTemp, transition = transitionSeconds)

          

p = Programs(pyscript.app_config)
