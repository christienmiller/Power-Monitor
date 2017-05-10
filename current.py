#!/usr/bin/python
 
from ISStreamer.Streamer import Streamer
from gpiozero import InputDevice
import smbus, logging, sys, time
import pyowm # open weather stuff
owm = pyowm.OWM('5ee48bfdfd0f00ca390e0450f8e600be')  # You MUST provide a valid API key


# Streamer constructor, this will create a bucket called Python Stream Example
# you'll be able to see this name in your list of logs on initialstate.com
# your access_key is a secret and is specific to you, don't share it!
streamer = Streamer(bucket_name="Energy Meter", bucket_key="energy_meter_bucket", access_key="CWsqEW2S6QI69NR2ZDhPml6MotNAfiPN")
 
DataReady = InputDevice(17, False) # look at GPIO for Data Ready from the ADC
 
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
logging.debug('A debug message!')
 
bus = smbus.SMBus(1)    # 0 = /dev/i2c-0 (port I2C0), 1 = /dev/i2c-1 (port I2C1)
 
DEVICE_ADDRESS = 0x2a      #7 bit address (will be left shifted to add the read write bit)
PU_CTRL = 0x00 # power up register
CTRL2 = 0x02 # control 2 register - channel select and calibrate
ADC_OUT_B0 = 0x14 # adc value registers
ADC_OUT_B1 = 0x13
ADC_OUT_B2 = 0x12
ch1 = 0 # current value of ch 1 scaled to current
ch2 = 0 # current value of ch 2 scaled to current 
ch1_calib = 34.755092634
ch2_calib = 40.434680254

# REG0x00:PU_CTRL
RR =	0
PUD =	1
PUA =	2
PUR =	3
CS =	4
CR =	5
OSCS =	6
AVDDS =	7

# REG0x02:CTRL2 
CALS =	2
CHS =	7

# Method to power up the device
def powerup():
	logging.debug('Running power up sequence')
	set_bit(PU_CTRL, RR) # set RR bit
	clear_bit(PU_CTRL, RR) # clear RR bit
	set_bit(PU_CTRL, PUD) # set PUD bit
	while not (bus.read_byte_data(DEVICE_ADDRESS, PU_CTRL) & 0x08): # wait for PUR bit
		logging.debug('waiting for power up')
	bus.write_byte_data(DEVICE_ADDRESS, PU_CTRL, 0x06) # set PUD bit and PUA bit
	return;

# Method to calibrate the device	
def calibrate():
	#logging.debug('Running calibration')
	set_bit(CTRL2, CALS)
	while (bus.read_byte_data(DEVICE_ADDRESS, CTRL2) & 0x04): # wait for calibration to complete
		no = 0x00
	#logging.debug('calibration done')
	return;

# Method to read ADC value of channel 1
def read_channel(channel, calib):
	if (channel == 1):
		clear_bit(CTRL2, CHS)
	elif (channel == 2):
		set_bit(CTRL2, CHS)
		
	calibrate() # need to re-calibrate before reading the value
	#logging.debug('PU_CTRL = %s', bus.read_byte_data(DEVICE_ADDRESS, PU_CTRL))
	while not (DataReady.is_active):
		no = 0x00 # logging.debug('waiting for DataReady') 
	#logging.debug('PU_CTRL = %s', bus.read_byte_data(DEVICE_ADDRESS, PU_CTRL))
	#logging.debug(' DataReady = %s', DataReady.is_active)
	reg3 = bus.read_byte_data(DEVICE_ADDRESS, ADC_OUT_B2)
	reg2 = bus.read_byte_data(DEVICE_ADDRESS, ADC_OUT_B1)
	reg1 = bus.read_byte_data(DEVICE_ADDRESS, ADC_OUT_B0)
	value = reg1 + (reg2 << 8) + (reg3 << 16)
	if (value & 0x800000):
		value = ~value+1;
		value = -1*(value & 0xFFFFFF);
	value = float(value) * calib / 16777216
	if (value < 0):
		value = 0
	#logging.debug('value = %.2f', value)

	return value; 

# set a bit, function takes register to modify and position in register to modify
def set_bit(reg, position):
	reg_value = bus.read_byte_data(DEVICE_ADDRESS, reg)
	bus.write_byte_data(DEVICE_ADDRESS, reg, reg_value | 1 << position)
	return

# clear a bit, function takes register to modify and position in register to modify
def clear_bit(reg, position):
	reg_value = bus.read_byte_data(DEVICE_ADDRESS, reg)
	bus.write_byte_data(DEVICE_ADDRESS, reg, reg_value & ~(1 << position))
	return


# Search for current weather in Edmonds
logging.debug('Searching for weather')
observation = owm.weather_at_place('Edmonds,Wa')
logging.debug('Getting current weather for found location')
weather = observation.get_weather()
logging.debug('current temp = %s', weather.get_temperature('fahrenheit')['temp'])	
# main
logging.debug('Powering up adc')
powerup()
#logging.debug('PU_CTRL = %s', bus.read_byte_data(DEVICE_ADDRESS, PU_CTRL))
calibrate()

start = time.time()
 
while (1):
	ch1 = read_channel(1, ch1_calib) # read channel 1
	ch2 = read_channel(2, ch2_calib) # read channel 2
	data = [ch1, ch2]
	#logging.debug(' data = %s', data)
	wattage = 230 * max(data)
	cost = ( wattage / 1000 ) * 0.10 # cost per hour using 10 cents per kW/h
	cost_s = cost / 3600
	start = time.time()
	logging.debug(' ch1 = %.2f amps, ch2 = %.2f amps, wattage = %.2f kw', ch1, ch2, wattage)
	streamer.log("L1", round(ch1, 2))
	streamer.log("L2", round(ch2, 2))
	streamer.log("Watts (w)", round(wattage, 1))
	streamer.log("Watts (kW)", round(wattage/1000, 3))
	streamer.log("Cost ($/hour)", round(cost, 3) )
	streamer.log("Cost ($/second)", cost_s)
	weather = observation.get_weather()
	streamer.log('outside_temp', round(weather.get_temperature('fahrenheit')['temp'], 1))	
