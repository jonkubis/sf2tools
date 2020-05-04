#!/usr/bin/python

import struct
import os
import array
import sys
from pathlib import Path

generatorEnumerators = ["startAddrsOffset","endAddrsOffset","startloopAddrsOffset","endloopAddrsOffset","startAddrsCoarseOffset","modLfoToPitch","vibLfoToPitch","modEnvToPitch","initialFilterFc","initialFilterQ","modLfoToFilterFc","modEnvToFilterFc","endAddrsCoarseOffset","modLfoToVolume","unused1","chorusEffectsSend","reverbEffectsSend","pan","unused2","unused3","unused4","delayModLFO","freqModLFO","delayVibLFO","freqVibLFO","delayModEnv","attackModEnv","holdModEnv","decayModEnv","sustainModEnv","releaseModEnv","keynumToModEnvHold","keynumToModEnvDecay","delayVolEnv","attackVolEnv","holdVolEnv","decayVolEnv","sustainVolEnv","releaseVolEnv","keynumToVolEnvHold","keynumToVolEnvDecay","instrument","reserved1","keyRange","velRange","startloopAddrsCoarseOffset","keynum","velocity","initialAttenuation","reserved2","endloopAddrsCoarseOffset","coarseTune","fineTune","sampleID","sampleModes","reserved3","scaleTuning","exclusiveClass","overridingRootKey","unused5","endOper"]

class SF2Archive(object):
	data = None
	size = None #file size minus the first 8 bytes of the RIFF header
	sampledataoffset = None
	sampledatalength = None
	pathname = None
	
	infochunk = None
	presetdatachunk = None
	
	def __init__(self):
		self.data = None
		self.size = None #file size minus the first 8 bytes of the RIFF header
		self.sampledataoffset = None
		self.sampledatalength = None
		self.pathname = None
			
		self.infochunk = None
		self.presetdatachunk = None
	
	def open(self, sf2file_name):
		with open(sf2file_name, 'rb') as sf2file:
			self.pathname = sf2file_name
			# read the header
			self.data = sf2file.read(12)
			if (self.data[0:4]) != b'RIFF': raise RuntimeError("RIFF header not detected!")
			size = struct.unpack_from('<I', self.data, 4)[0]
			if (self.data[8:12]) != b'sfbk': raise RuntimeError("sfbk header not detected!")
			
			#now we read chunk-by-chunk
			for x in range(3):
				chunkheader = sf2file.read(12)
				if (chunkheader[0:4]) != b'LIST': raise RuntimeError("LIST header not detected!")
				chunksize = struct.unpack_from('<I', chunkheader, 4)[0] - 4 #minus 4 for the 'INFO' tag
				chunktag = chunkheader[8:12]
				if (chunktag == b'INFO'): #SoundFont Info Chunk
					chunkdata = sf2file.read(chunksize)
					self.infochunk = SF2InfoChunk()
					self.infochunk.parse(chunkdata)
				elif (chunktag == b'sdta'): #Sample Data Chunk -- we're gonna take notes, but not load the samples into memory
					if (sf2file.read(4)) != b'smpl': raise RuntimeError("smpl subheader not detected!")
					self.sampledatalength = struct.unpack_from('<I', sf2file.read(4), 0)[0]
					self.sampledataoffset = sf2file.tell()
					sf2file.seek(self.sampledataoffset + self.sampledatalength) #skip past sampledata
				elif (chunktag == b'pdta'): #Preset Data Chunk
					chunkdata = sf2file.read(chunksize)
					self.presetdatachunk = SF2PresetDataChunk(self)
					self.presetdatachunk.parse(chunkdata)
					
	def writeSF2(self,sf2file_name):
		with open(sf2file_name, 'wb') as outfile:
			outfile.write(b'RIFF')
			outfile.write(b'\x00\x00\x00\x00') #we'll write over this later
			outfile.write(b'sfbk')
			outfile.write(b'LIST')
			towrite = self.infochunk.export()
			outfile.write(struct.pack("<I",len(towrite)))
			outfile.write(towrite)
			
			outfile.write(b'LIST')
			sampledatatotal = 0
			for x in self.presetdatachunk.samples:
				sampledatatotal += len(x.sampledata) + 92 #92 BYTES padding between samples
				
			outfile.write(struct.pack("<I",sampledatatotal+12))
			outfile.write(b'sdtasmpl')
			outfile.write(struct.pack("<I",sampledatatotal))
			
			sampledatastartoffset = outfile.tell()
			
			for x in self.presetdatachunk.samples:
				currentsampleoffset = int((outfile.tell() - sampledatastartoffset) / 2)
				
				x.exportstart     = currentsampleoffset
				x.exportend       = currentsampleoffset + (x.end - x.start)
				x.exportstartloop = currentsampleoffset + (x.startloop - x.start)
				x.exportendloop   = currentsampleoffset + (x.endloop - x.start)
				outfile.write(x.sampledata)
				outfile.write(b'\x00' * 92)
				
			outfile.write(b'LIST')
			towrite = self.presetdatachunk.export()
			
			towrite.extend(b'pbag')
			towrite.extend(struct.pack("<I",(len(self.presetdatachunk.presetzones)+1)*4))
			for x in self.presetdatachunk.presetzones:
				towrite.extend(struct.pack("<H",x.generatorIndex))
				towrite.extend(struct.pack("<H",x.modIndex))
				
			#terminator
			towrite.extend(struct.pack("<H",x.generatorIndex+2))
			towrite.extend(struct.pack("<H",x.modIndex))
			
			towrite.extend(b'pmod')
			towrite.extend(struct.pack("<I",(len(self.presetdatachunk.presetzonemodulators)*10)))
			towrite.extend(b'\x00' * 10)
			
			towrite.extend(b'pgen')
			towrite.extend(struct.pack("<I",((len(self.presetdatachunk.presetzonegenerators)+1)*4)))
			for x in self.presetdatachunk.presetzonegenerators:
				towrite.extend(struct.pack("<H",x.operator))
				towrite.extend(struct.pack("<h",x.amount))
			
			towrite.extend(b'\x00' * 4)
			
			towrite.extend(b'inst')
			towrite.extend(struct.pack("<I",((len(self.presetdatachunk.instruments)+1)*22)))
			
			
			for x in self.presetdatachunk.instruments:
				towrite.extend(x.name.strip().ljust(20,'\x00').encode())
				towrite.extend(struct.pack("<H",x.bagindex))
			
			towrite.extend(b'\x00'*20)
			towrite.extend(struct.pack("<H",x.bagindex + 1))
			
			towrite.extend(b'ibag')
			towrite.extend(struct.pack("<I",((len(self.presetdatachunk.instrumentzones)+1)*4)))
			for x in self.presetdatachunk.instrumentzones:
				towrite.extend(struct.pack("<H",x.generatorIndex))
				towrite.extend(struct.pack("<H",x.modIndex))
				
			towrite.extend(struct.pack("<H",x.generatorIndex+11))
			towrite.extend(struct.pack("<H",x.modIndex))
			
			towrite.extend(b'imod')
			towrite.extend(struct.pack("<I",(len(self.presetdatachunk.instrumentzonemodulators)*10)))
			towrite.extend(b'\x00' * 10)
			
			towrite.extend(b'igen')
			towrite.extend(struct.pack("<I",((len(self.presetdatachunk.instrumentzonegenerators)+1)*4)))
			for x in self.presetdatachunk.instrumentzonegenerators:
				towrite.extend(struct.pack("<H",x.operator))
				towrite.extend(struct.pack("<h",x.amount))
				
			towrite.extend(b'\x00' * 4)
			
			towrite.extend(b'shdr')
			towrite.extend(struct.pack("<I",((len(self.presetdatachunk.samples)+1)*46)))
			for x in self.presetdatachunk.samples:
				towrite.extend(x.name.strip().ljust(20,'\x00').encode())
				towrite.extend(struct.pack("<I",x.exportstart))
				towrite.extend(struct.pack("<I",x.exportend))
				towrite.extend(struct.pack("<I",x.exportstartloop))
				towrite.extend(struct.pack("<I",x.exportendloop))
				towrite.extend(struct.pack("<I",x.samplerate))
				towrite.extend(struct.pack( "B",x.rootnote))
				towrite.extend(struct.pack( "b",x.finetune))
				towrite.extend(struct.pack("<H",x.link))
				towrite.extend(struct.pack("<H",x.sampletype))
			
			towrite.extend(b'\x00' * 46)
			
			
			outfile.write(struct.pack("<I",len(towrite)))
			outfile.write(towrite)
						
			totalsize = outfile.tell()
			outfile.seek(4)
			outfile.write(struct.pack("<I",totalsize-8))
			
	
					
	def unusedPresetName(self):
		trimmedname = self.presetdatachunk.presets[-1].name.strip()
		if (trimmedname[-1].isnumeric()):
			ctr = 1
			while (trimmedname[-1 * ctr:].isnumeric()):
				ctr += 1
			
			ctr -= 1
			identifier = int(trimmedname[-1 * ctr:]) + 1
			return (trimmedname[:-1 * ctr] + str(identifier))
			
		else: #just add '1' and go
			return (trimmedname + '1')

	def unusedInstrumentName(self):
		trimmedname = self.presetdatachunk.instruments[-1].name.strip()
		if (trimmedname[-1].isnumeric()):
			ctr = 1
			while (trimmedname[-1 * ctr:].isnumeric()):
				ctr += 1
			
			ctr -= 1
			identifier = int(trimmedname[-1 * ctr:]) + 1
			return (trimmedname[:-1 * ctr] + str(identifier))
			
		else: #just add '1' and go
			return (trimmedname + '1')
			
	def unusedSampleName(self):
		trimmedname = self.presetdatachunk.samples[-1].name.strip()
		if (trimmedname[-1].isnumeric()):
			ctr = 1
			while (trimmedname[-1 * ctr:].isnumeric()):
				ctr += 1
			
			ctr -= 1
			identifier = int(trimmedname[-1 * ctr:]) + 1
			return (trimmedname[:-1 * ctr] + str(identifier))
			
		else: #just add '1' and go
			return (trimmedname + '1')
			
	def unusedSampleNameFromBaseName(self,basename):
		trimmedname = basename.strip()
		newname = trimmedname
		ctr = 1
			
		if (newname[-1].isnumeric() == False):
			newname = (trimmedname + '1')
				
		while self.sampleNameAlreadyExists(newname):
			while (newname[-1 * ctr:].isnumeric()):
				ctr += 1
					
			ctr -= 1
			identifier = int(newname[-1 * ctr:]) + 1
			newname = (newname[:-1 * ctr] + str(identifier))
				
		return newname
		
	def unusedInstrumentNameFromBaseName(self,basename):
			trimmedname = basename.strip()
			newname = trimmedname
			ctr = 1
				
			if (newname[-1].isnumeric() == False):
				newname = (trimmedname + '1')
					
			while self.instrumentNameAlreadyExists(newname):
				while (newname[-1 * ctr:].isnumeric()):
					ctr += 1
						
				ctr -= 1
				identifier = int(newname[-1 * ctr:]) + 1
				newname = (newname[:-1 * ctr] + str(identifier))
					
			return newname
			
	def unusedPresetNameFromBaseName(self,basename):
				trimmedname = basename.strip()
				newname = trimmedname
				ctr = 1
					
				if (newname[-1].isnumeric() == False):
					newname = (trimmedname + '1')
						
				while self.presetNameAlreadyExists(newname):
					while (newname[-1 * ctr:].isnumeric()):
						ctr += 1
							
					ctr -= 1
					identifier = int(newname[-1 * ctr:]) + 1
					newname = (newname[:-1 * ctr] + str(identifier))
						
				return newname
		
	def sampleNameAlreadyExists(self,samplename):
		for x in self.presetdatachunk.samples:
			if (x.name == samplename):
				return True
		return False
		
	def instrumentNameAlreadyExists(self,instrumentname):
			for x in self.presetdatachunk.instruments:
				if (x.name == instrumentname):
					return True
			return False
	
	def presetNameAlreadyExists(self,presetname):
				for x in self.presetdatachunk.presets:
					if (x.name == presetname):
						return True
				return False

class SF2InfoChunk(object):
	data = None
	size = None
	
	version     = None #ifil
	soundengine = None #isng
	name        = None #INAM
	romname     = None #irom
	romversion  = None #iver
	date        = None #ICRD
	engineers   = None #IENG
	product     = None #IPRD
	copyright   = None #ICOP
	comments    = None #ICMT
	tool        = None #ISFT
	
	def parse(self, theData):
		self.data = theData
		self.size = len(theData)
		pos = 0
		
		while (pos < len(self.data)):
			subchunktag = self.data[pos:pos+4]
			subchunksize = struct.unpack_from('<I', self.data[pos+4:pos+8], 0)[0]
			subchunkdata = self.data[pos+8:pos+8+subchunksize]
			if (subchunktag == b'ifil'):
				self.version = str(struct.unpack_from('<H', subchunkdata, 0)[0]) + '.' + str(struct.unpack_from('<H', subchunkdata, 2)[0])
			if (subchunktag == b'INAM'): self.name        = subchunkdata.decode('utf-8')
			if (subchunktag == b'isng'): self.soundengine = subchunkdata.decode('utf-8')
			if (subchunktag == b'irom'): self.romname     = subchunkdata.decode('utf-8')
			if (subchunktag == b'iver'):
				self.romversion = str(struct.unpack_from('<H', subchunkdata, 0)[0]) + '.' + str(struct.unpack_from('<H', subchunkdata, 2)[0])
			if (subchunktag == b'ICRD'): self.date        = subchunkdata.decode('utf-8')
			if (subchunktag == b'IENG'): self.engineers   = subchunkdata.decode('utf-8')
			if (subchunktag == b'IPRD'): self.product     = subchunkdata.decode('utf-8')
			if (subchunktag == b'ICOP'): self.copyright   = subchunkdata.decode('utf-8')
			if (subchunktag == b'ICMT'): self.comments    = subchunkdata.decode('utf-8')
			if (subchunktag == b'ISFT'): self.tool        = subchunkdata.decode('utf-8')
			pos += (8 + subchunksize)
			
	def export(self):
		toexport = bytearray(b'INFO')
		if (self.version is not None):
			toexport.extend(b'ifil')
			toexport.extend(struct.pack('<I', 4))
			major = self.version.split('.')[0]
			minor = self.version.split('.')[1]
			toexport.extend(struct.pack('<H', int(major)))
			toexport.extend(struct.pack('<H', int(minor)))
		if (self.soundengine is not None):
			toexport.extend(b'isng')
			toexport.extend(struct.pack('<I', len(self.soundengine)))
			toexport.extend(self.soundengine.encode())
		if (self.name is not None):
			toexport.extend(b'INAM')
			toexport.extend(struct.pack('<I', len(self.name)))
			toexport.extend(self.name.encode())
		if (self.date is not None):
			toexport.extend(b'ICRD')
			toexport.extend(struct.pack('<I', len(self.date)))
			toexport.extend(self.date.encode())
		if (self.tool is not None):
			toexport.extend(b'ISFT')
			toexport.extend(struct.pack('<I', len(self.tool)))
			toexport.extend(self.tool.encode())
		return toexport
	
class SF2PresetDataChunk(object):
	
	sf2arch = None
	
	data = None
	size = None
	presetcount = None
	presetzonecount = None
	presetzonegeneratorcount = None
	presetzonemodulatorcount = None
	instrumentcount = None
	instrumentzonecount = None
	instrumentzonegeneratorcount = None
	instrumentzonemodulatorcount = None
	
	presets = None
	presetzones = None
	presetzonegenerators = None
	presetzonemodulators = None
	instruments = None
	instrumentzones = None
	instrumentzonegenerators = None
	instrumentzonemodulators = None
	samples = None
	
	def __init__(self,thearchive):
		self.sf2arch = thearchive
		self.presets = []
		self.presetzones = []
		self.presetzonegenerators = []
		self.presetzonemodulators = []
		self.instruments = []
		self.instrumentzones = []
		self.instrumentzonegenerators = []
		self.instrumentzonemodulators = []
		self.samples = []
	
	def parse(self, theData):
		self.data = theData
		self.size = len(theData)
		pos = 0
	
		while (pos < len(self.data)):
			subchunktag = self.data[pos:pos+4]
			subchunksize = struct.unpack_from('<I', self.data[pos+4:pos+8], 0)[0]
			subchunkdata = self.data[pos+8:pos+8+subchunksize]
			if (subchunktag == b'phdr'): #preset listing
				self.presetcount = int(subchunksize / 38) #each preset header is 38 bytes wide
				for x in range(self.presetcount):
					thispreset = SF2Preset() #create a new preset
					thispreset.parseheader(subchunkdata[x * 38: (x+1) * 38])
					self.presets.append(thispreset)
			elif (subchunktag == b'pbag'): #preset zones
				self.presetzonecount = int(subchunksize / 4) #each preset zone is 4 bytes wide
				for x in range(self.presetzonecount):
					thispresetzone = SF2PresetZone() #create a new preset zone
					thispresetzone.parse(subchunkdata[x * 4: (x+1) * 4])
					self.presetzones.append(thispresetzone)
			elif (subchunktag == b'pmod'): #preset zone modulators
				self.presetzonemodulatorcount = int(subchunksize / 10) #each preset zone modulator is 10 bytes wide
				for x in range(self.presetzonemodulatorcount):
					thispresetzonemodulator = SF2PresetZoneModulator() #create a new preset zone generator
					thispresetzonemodulator.parse(subchunkdata[x * 10: (x+1) * 10])
					self.presetzonemodulators.append(thispresetzonemodulator)
			elif (subchunktag == b'pgen'): #preset zone generators
				self.presetzonegeneratorcount = int(subchunksize / 4) #each preset zone is 4 bytes wide
				for x in range(self.presetzonegeneratorcount):
					thispresetzonegenerator = SF2PresetZoneGenerator() #create a new preset zone generator
					thispresetzonegenerator.parse(subchunkdata[x * 4: (x+1) * 4])
					self.presetzonegenerators.append(thispresetzonegenerator)
			elif (subchunktag == b'inst'): #instruments
				self.instrumentcount = int(subchunksize / 22) #each instrument is 22 bytes wide
				for x in range(self.instrumentcount):
					thisinstrument = SF2Instrument() #create a new instrument
					thisinstrument.parse(subchunkdata[x * 22: (x+1) * 22])
					self.instruments.append(thisinstrument)
			elif (subchunktag == b'ibag'): #instrument zones
				self.instrumentzonecount = int(subchunksize / 4) #each instrument zone is 4 bytes wide
				for x in range(self.instrumentzonecount):
					thisinstrumentzone = SF2InstrumentZone() #create a new instrument zone
					thisinstrumentzone.parse(subchunkdata[x * 4: (x+1) * 4])
					self.instrumentzones.append(thisinstrumentzone)
			elif (subchunktag == b'imod'): #instrument zone modulators
				self.instrumentzonemodulatorcount = int(subchunksize / 10) #each instrument zone modulator is 10 bytes wide
				for x in range(self.instrumentzonemodulatorcount):
					thisinstrumentzonemodulator = SF2InstrumentZoneModulator() #create a new preset zone generator
					thisinstrumentzonemodulator.parse(subchunkdata[x * 10: (x+1) * 10])
					self.instrumentzonemodulators.append(thisinstrumentzonemodulator)
			elif (subchunktag == b'igen'): #instrument zone generators
				self.instrumentzonegeneratorcount = int(subchunksize / 4) #each preset zone is 4 bytes wide
				for x in range(self.instrumentzonegeneratorcount):
					thisinstrumentzonegenerator = SF2InstrumentZoneGenerator() #create a new preset zone generator
					thisinstrumentzonegenerator.parse(subchunkdata[x * 4: (x+1) * 4])
					self.instrumentzonegenerators.append(thisinstrumentzonegenerator)
			elif (subchunktag == b'shdr'): #sample listing
				presetcount = int(subchunksize / 46) #each preset header is 46 bytes wide
				for x in range(presetcount):
					thissample = SF2Sample(self.sf2arch) #create a new sample
					thissample.parseheader(subchunkdata[x * 46: (x+1) * 46])
					thissample.loadsampledata()
					self.samples.append(thissample)
			else:
				print (subchunktag)
						
			pos += (8 + subchunksize)
		
		for x in range(1,len(self.presets)):
			self.presets[x-1].hizonenumber = self.presets[x].lowzonenumber - 1
		
		for thispreset in self.presets:
			for x in range(thispreset.lowzonenumber,thispreset.hizonenumber+1):
				thispreset.zones.append(self.presetzones[x])
		
		for x in range(1,len(self.presets)):
			self.presets[x-1].zones[-1].higeneratornumber = self.presets[x].zones[0].lowgeneratornumber - 1
		
		for thispreset in self.presets:
			for x in range(1,len(thispreset.zones)):
				thispreset.zones[x-1].higeneratornumber = thispreset.zones[x].lowgeneratornumber - 1
		
		for thispreset in self.presets:
			for thiszone in thispreset.zones:
				for x in range(thiszone.lowgeneratornumber,thiszone.higeneratornumber+1):
					thiszone.generators.append(self.presetzonegenerators[x])

		for x in range(1,len(self.instruments)):
			self.instruments[x-1].hizonenumber = self.instruments[x].lowzonenumber - 1
			
		for thisinstrument in self.instruments:
			for x in range(thisinstrument.lowzonenumber,thisinstrument.hizonenumber+1):
				thisinstrument.zones.append(self.instrumentzones[x])
				
		for x in range(1,len(self.instruments)):
			self.instruments[x-1].zones[-1].higeneratornumber = self.instruments[x].zones[0].lowgeneratornumber - 1
		
		for thisinstrument in self.instruments:
			for x in range(1,len(thisinstrument.zones)):
				thisinstrument.zones[x-1].higeneratornumber = thisinstrument.zones[x].lowgeneratornumber - 1
				
		for thisinstrument in self.instruments:
			for thiszone in thisinstrument.zones:
				for x in range(thiszone.lowgeneratornumber,thiszone.higeneratornumber+1):
					thiszone.generators.append(self.instrumentzonegenerators[x])
		
		for x in range(len(self.presets)): self.presets[x].identifier = x
		for x in range(len(self.instruments)): self.instruments[x].identifier = x
		for x in range(len(self.samples)): self.samples[x].identifier = x
		
		for thisinstrument in self.instruments:
			for thisinstrumentzone in thisinstrument.zones:
				for thisinstrumentzonegenerator in thisinstrumentzone.generators:
					if (thisinstrumentzonegenerator.operator == 53):
						thisinstrument.firstsample = self.samples[thisinstrumentzonegenerator.amount]
						break
				if (thisinstrument.firstsample is not None): break
		
		for thispreset in self.presets:
			for thispresetzone in thispreset.zones:
				for thispresetzonegenerator in thispresetzone.generators:
					if (thispresetzonegenerator.operator == 41):
						thispreset.firstinstrument = self.instruments[thispresetzonegenerator.amount]
						thispreset.firstsample = thispreset.firstinstrument.firstsample
						thispreset.firstsample.firstinstrument = thispreset.firstinstrument
						thispreset.firstsample.firstpreset = thispreset
						break
				if (thispreset.firstinstrument is not None): break
		
		#wipe out terminators
		if (self.presets[-1].firstinstrument is None):
			while (len(self.presetzones) > self.presets[-1].bagindex):
				while len(self.presetzonegenerators) > self.presetzones[-1].generatorIndex:
					del(self.presetzonegenerators[-1])
				del(self.presetzones[-1])
			del(self.presets[-1])
			
		if (self.instruments[-1].firstsample is None): 
			while (len(self.instrumentzones) > self.instruments[-1].bagindex):
				while len(self.instrumentzonegenerators) > self.instrumentzones[-1].generatorIndex:
					del(self.instrumentzonegenerators[-1])
				del(self.instrumentzones[-1])
			del(self.instruments[-1])
		if (self.samples[-1].end == 0): del(self.samples[-1])
		
		
	def export(self):
		toexport = bytearray(b'pdtaphdr')
		toexport.extend(struct.pack('<I',(len(self.presets)+1) * 38))
		for x in self.presets:
			thename = bytearray(x.name.strip().ljust(20,'\x00').encode())
			toexport.extend(thename)
			toexport.extend(struct.pack('<H',x.number))
			toexport.extend(struct.pack('<H',x.bank))
			toexport.extend(struct.pack('<H',x.bagindex))
			toexport.extend(struct.pack('<I',x.library))
			toexport.extend(struct.pack('<I',x.genre))
			toexport.extend(struct.pack('<I',x.morph))
			
		#create a terminating chunk
		toexport.extend(b'\x00' * 24)
		toexport.extend(struct.pack('<H',x.bagindex + 1))
		toexport.extend(b'\x00' * 12)
			
		return toexport
					
		
class SF2Preset(object):
	firstinstrument = None
	firstsample = None
	headerdata = None
	data = None
	size = None	
	identifier = None
	
	name   = None
	number = None
	bank   = None
	bagindex  = None
	
	library = None
	genre   = None
	morph   = None
	
	zones   = None
	lowzonenumber = None
	hizonenumber  = None
	
	zonecount = 1

	def __init__(self):
		self.zones = []

	def parseheader(self, theData):
		self.headerdata = theData
		
		terminator = self.headerdata[0:20].find(b'\x00')
		if terminator == -1: terminator = 20 #in case no string terminator found in the 20 characters
		self.name = self.headerdata[0:terminator].decode('utf-8').ljust(20)
		
		self.number  = struct.unpack_from('<H', self.headerdata, 20)[0]
		self.bank    = struct.unpack_from('<H', self.headerdata, 22)[0]
		self.bagindex   = struct.unpack_from('<H', self.headerdata, 24)[0]
		self.lowzonenumber = self.bagindex
		self.hizonenumber = self.bagindex
		
		self.library = struct.unpack_from('<I', self.headerdata, 26)[0]
		self.genre   = struct.unpack_from('<I', self.headerdata, 30)[0]
		self.morph   = struct.unpack_from('<I', self.headerdata, 34)[0]

class SF2PresetZone(object):
	data = None
	size = None
	
	generators = None
	
	generatorIndex = None
	lowgeneratornumber = None
	higeneratornumber = None
	modIndex = None
	
	def __init__(self):
		self.generators = []
	
	def parse(self, theData):
		self.data = theData
		self.generatorIndex  = struct.unpack_from('<H', self.data, 0)[0]
		self.lowgeneratornumber = self.generatorIndex
		self.higeneratornumber = self.generatorIndex
		self.modIndex        = struct.unpack_from('<H', self.data, 2)[0]
		

class SF2PresetZoneModulator(object):
	data = None
	size = None
	
	def parse(self, theData):
		self.data = theData
		

class SF2PresetZoneGenerator(object):
	data = None
	size = None
	
	operator = None
	amount = None
	amountunsigned = None
	amountrangel = None
	amountrangeh = None
	
	#kStartAddrsOffset = 0, 
	#kEndAddrsOffset, kStartloopAddrsOffset, kEndloopAddrsOffset,
	#	kStartAddrsCoarseOffset, kModLfoToPitch, kVibLfoToPitch, kModEnvToPitch,
	#	kInitialFilterFc, kInitialFilterQ, kModLfoToFilterFc, kModEnvToFilterFc,
	#	kEndAddrsCoarseOffset, kModLfoToVolume, kUnused1, kChorusEffectsSend,
	#	kReverbEffectsSend, kPan, kUnused2, kUnused3,
	#	kUnused4, kDelayModLFO, kFreqModLFO, kDelayVibLFO,
	#	kFreqVibLFO, kDelayModEnv, kAttackModEnv, kHoldModEnv,
	#	kDecayModEnv, kSustainModEnv, kReleaseModEnv, kKeynumToModEnvHold,
	#	kKeynumToModEnvDecay, kDelayVolEnv, kAttackVolEnv, kHoldVolEnv,
	#	kDecayVolEnv, kSustainVolEnv, kReleaseVolEnv, kKeynumToVolEnvHold,
	#	kKeynumToVolEnvDecay, kInstrument, kReserved1, kKeyRange,
	#	kVelRange, kStartloopAddrsCoarseOffset, kKeynum, kVelocity,
	#	kInitialAttenuation, kReserved2, kEndloopAddrsCoarseOffset, kCoarseTune,
	#	kFineTune, kSampleID, kSampleModes, kReserved3,
	#	kScaleTuning, kExclusiveClass, kOverridingRootKey, kUnused5,
	#	kEndOper
	
	# 16 = REVERB % -- 700 = 70.0%
	
	def parse(self, theData):
		self.data = theData
		self.operator  = struct.unpack_from('<H', self.data, 0)[0]
		self.amount    = struct.unpack_from('<h', self.data, 2)[0]
		self.amountunsigned = struct.unpack_from('<H', self.data, 2)[0]
		self.amountrangel = struct.unpack_from('B', self.data, 2)[0]
		self.amountrangeh = struct.unpack_from('B', self.data, 3)[0]
		
class SF2Instrument(object):
	firstsample = None
	data = None
	size = None
	identifier = None
	
	name = None
	bagindex = None
	
	lowzonenumber = None
	hizonenumber  = None
	
	zones   = None	
	
	def __init__(self):
		self.zones = []
	
	def parse(self, theData):
		self.data = theData
		terminator = self.data[0:20].find(b'\x00')
		if terminator == -1: terminator = 20 #in case no string terminator found in the 20 characters
		self.name = self.data[0:terminator].decode('utf-8').ljust(20)
		self.bagindex  = struct.unpack_from('<H', self.data, 20)[0]
		self.lowzonenumber = self.bagindex
		self.hizonenumber = self.bagindex
		
class SF2InstrumentZone(object):
	data = None
	size = None
	
	generators = None
	
	generatorIndex = None
	lowgeneratornumber = None
	higeneratornumber = None
	modIndex = None
	
	def __init__(self):
		self.generators = []
	
	def parse(self, theData):
		self.data = theData
		self.generatorIndex  = struct.unpack_from('<H', self.data, 0)[0]
		self.lowgeneratornumber = self.generatorIndex
		self.higeneratornumber = self.generatorIndex
		self.modIndex        = struct.unpack_from('<H', self.data, 2)[0]

class SF2InstrumentZoneModulator(object):
	data = None
	size = None
	
	def parse(self, theData):
		self.data = theData

class SF2InstrumentZoneGenerator(object):
	data = None
	size = None
	
	operator = None
	amount = None
	amountunsigned = None
	amountrangel = None
	amountrangeh = None
		
	def parse(self, theData):
		self.data = theData
		self.operator  = struct.unpack_from('<H', self.data, 0)[0]
		self.amount    = struct.unpack_from('<h', self.data, 2)[0]
		self.amountunsigned = struct.unpack_from('<H', self.data, 2)[0]
		self.amountrangel = struct.unpack_from('B', self.data, 2)[0]
		self.amountrangeh = struct.unpack_from('B', self.data, 3)[0]

class SF2Sample(object):
	firstinstrument = None
	firstpreset = None
	matched = False
	
	sf2arch = None
	
	headerdata = None
	__sampledata = None
	data       = None
	size       = None
	identifier = None
	
		
	name       = None
	#start/end/startloop/endloop are all pointers into the gigantic sample data chunk...
	start      = None
	end        = None
	startloop  = None
	endloop    = None
	
	localstart = None
	localend   = None
	localstartloop = None
	localendloop   = None
	
	samplerate = None
	rootnote   = None
	finetune   = None
	link       = None
	sampletype = None # 1 = monoSample, 2 = rightSample, 4 = leftSample, 8 = linkedSample, 32769 = romMonoSample, 32770 = romRightSample, 32772 = romLeftSample, 32776 = romLinkedSample
	
	sampledataloaded = False
	
	def __init__(self,thearchive):
		self.sf2arch = thearchive
	
	def parseheader(self, theData):
		self.headerdata = theData
		
		terminator = self.headerdata[0:20].find(b'\x00')
		if terminator == -1: terminator = 20 #in case terminator wasn't found in the 20 characters
		self.name = self.headerdata[0:terminator].decode('utf-8').ljust(20)
		
		self.start      = struct.unpack_from('<I', self.headerdata, 20)[0]
		self.end        = struct.unpack_from('<I', self.headerdata, 24)[0]
		self.startloop  = struct.unpack_from('<I', self.headerdata, 28)[0]
		self.endloop    = struct.unpack_from('<I', self.headerdata, 32)[0]

		self.exportstart = 0
		self.exportend = 0
		self.exportstartloop = 0
		self.exportendloop = 0
		self.samplerate = struct.unpack_from('<I', self.headerdata, 36)[0]
		self.rootnote   = struct.unpack_from( 'B', self.headerdata, 40)[0]
		self.finetune   = struct.unpack_from( 'b', self.headerdata, 41)[0]
		self.link       = struct.unpack_from('<H', self.headerdata, 42)[0]
		self.sampletype = struct.unpack_from('<H', self.headerdata, 44)[0]
	
	def loadsampledata(self):
		with open(self.sf2arch.pathname, 'rb') as sf2file:
			sf2file.seek(self.sf2arch.sampledataoffset + (self.start * 2))
			ckSize = (self.end - self.start) * 2 #samples to bytes (16bit) 
			self.__sampledata = sf2file.read(ckSize)
		self.sampledataloaded = True
		
	def writeWAV(self,pathname):
		with open(pathname, 'wb') as fo:
			fo = open(outfile,"wb")
			ckSize = (self.end - self.start) * 2 #samples to bytes (16bit) 
			loopstart = (self.startloop - self.start)
			loopend = (self.endloop - self.start)

			rawdata = self.sampledata
			wSamplesPerSec = self.samplerate
			wChannels = 1

			fo.write(str.encode('RIFF')+b"\x00\x00\x00\x00"+str.encode('WAVEfmt '))
			fo.write(struct.pack('I', 16)) #chunk length
			fo.write(struct.pack('H', 1))  #pcm format
			fo.write(struct.pack('H', wChannels)) # channel count 
			fo.write(struct.pack('I', wSamplesPerSec)) # sample rate
			fo.write(struct.pack('I', int((wSamplesPerSec * wChannels * 16) / 8)))
			fo.write(struct.pack('H', int((wChannels * 16) / 8)))
			fo.write(struct.pack('H', 16)) #16 bit

			fo.write(b'smpl')
			fo.write(struct.pack('I', 60)) #chunk length
			fo.write(b'\x00\x00\x00\x00\x00\x00\x00\x00')
			fo.write(struct.pack('I', int((1/wSamplesPerSec)*1000000000))) #nanoseconds per sample
			#rootnote = int(os.path.splitext(filename)[0].split('-')[-1])
			fo.write(struct.pack('I', thesample.rootnote))
			fo.write(b'\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00')
			fo.write(struct.pack('I', 1)) # 1 sample loop follows
			fo.write(struct.pack('I', 0)) # of size 24 bytes...
			fo.write(struct.pack('I', 1)) # cue point 1
			fo.write(struct.pack('I', 0)) # loop forward
			fo.write(struct.pack('I', loopstart * wChannels)) # byte offset to start of loop
			fo.write(struct.pack('I', (loopend-1) * wChannels)) # byte offset to start of loop
			fo.write(b'\x00\x00\x00\x00\x00\x00\x00\x00')

			fo.write(b'data')
			fo.write(struct.pack('I', int(len(rawdata))))
			fo.write(rawdata)

			filesize = fo.tell()
			fo.seek(4)
			fo.write(struct.pack('I', int(filesize-8)))
	
	@property
	def sampledata(self):
		if (self.sampledataloaded == False):
			with open(self.sf2arch.pathname, 'rb') as sf2file:
				sf2file.seek(self.sf2arch.sampledataoffset + (self.start * 2))
				ckSize = (self.end - self.start) * 2 #samples to bytes (16bit) 
				return (sf2file.read(ckSize))
		else:
			return self.__sampledata
	
	def importsampledata(self,newsampledata):
		self.__sampledata = newsampledata
		self.sampledataloaded = True
