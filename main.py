
import zlib
import math
import pygame
import sys

dat = None

def pull(o, count, offset=0):
	t = o[offset:count]
	o = o[offset + count:]
	return o, t

def pullint(o, count, offset=0, endian="big"):
	o, a = pull(o, count, offset=offset)
	return o, int.from_bytes(a, endian)

def dec(byte_array, place):
	return int.from_bytes(byte_array[place:place+1], "big")

class PNGChunk:
	length = 0
	ctype = b""
	data = b""
	crc = b""

	alt_data = {}

	def read_from(self, dat):
		dat, self.length = pullint(dat, 4)
		dat, self.ctype = pull(dat, 4)
		dat, self.data = pull(dat, self.length)
		dat, self.crc = pull(dat, 4)

		d = self.data
		self.alt_data = {}

		if self.ctype == b"IHDR":
			d, self.alt_data["width"] = pullint(d, 4)
			d, self.alt_data["height"] = pullint(d, 4)
			d, self.alt_data["bit_depth"] = pullint(d, 1)
			d, self.alt_data["color_type"] = pullint(d, 1)
			d, self.alt_data["compression_method"] = pullint(d, 1)
			d, self.alt_data["filter_method"] = pullint(d, 1)
			d, self.alt_data["interlace_method"] = pullint(d, 1)
		if self.ctype == b"sRGB":
			d, self.alt_data["rendering_intent"] = pullint(d, 1)
		if self.ctype == b"pHYs":
			d, self.alt_data["ppu_x"] = pullint(d, 4)
			d, self.alt_data["ppu_y"] = pullint(d, 4)
			d, self.alt_data["unit_spec"] = pullint(d, 1)
		if self.ctype == b"gAMA":
			d, self.alt_data["gamma"] = pullint(d, 4)

		return dat
	
	def data_as_readable_hex(self):
		t = iter(self.data.hex())
		return " ".join(a + b for a, b in zip(t, t))

	def log(self, should_log_data=False):
		print(f"Chunk {self.ctype}")
		print(f"  Chunk length: {self.length}")
		print(f"  Chunk type: {self.ctype}")
		if should_log_data:
			print(f"  Chunk data: {self.data}")
		else:
			print(f"  Not logging data (is of size {len(self.data)})")
		print(f"  Alt data: {self.alt_data}")
		print(f"  CRC: {self.crc}")

		if self.ctype == b"pHYs":
			if self.alt_data["unit_spec"] == 1:
				print(f"    pHYs: Pixel size included.")
				x = (1 / self.alt_data["ppu_x"]) * 1000
				print(f"    pHYs: 1 pixel = {x} mm")

class PNGImage:
	chunks = []
	width = 0
	height = 0
	bit_depth = 0
	color_type = 0
	compression_method = 0
	filter_method = 0
	interlace_method = 0

	raw_data = []

	#
	decompressed_data = b""
	unfiltered_data = b""

	def read_from(self, dat):
		cur_name = b""

		while cur_name != b"IEND":
			# load another chunk
			chunk = PNGChunk()
			dat = chunk.read_from(dat)
			#chunk.log()

			cur_name = chunk.ctype

			if chunk.ctype == b"IHDR":
				self.width = chunk.alt_data["width"]
				self.height = chunk.alt_data["height"]
				self.bit_depth = chunk.alt_data["bit_depth"]
				self.color_type = chunk.alt_data["color_type"]
				self.compression_method = chunk.alt_data["compression_method"]
				self.filter_method = chunk.alt_data["filter_method"]
				self.interlace_method = chunk.alt_data["interlace_method"]

			# append chunk to list
			self.chunks.append(chunk)
	
	def get_first_chunk(self, ctype):
		for chunk in self.chunks:
			if chunk.ctype == ctype:
				return chunk
	
	def debug_data_log(self):
		idat = self.get_first_chunk(b"IDAT")

		d = idat.data

		print(d[0:20].hex())

		d, idat_comp_method = pullint(d, 1)
		d, idat_addit_flags = pullint(d, 1)
		d, idat_comp_data = pull(d, len(d) - 4)
		d, idat_check_value = pull(d, 4)

		"""
		print(f"- IDAT Compression method/flags code: {idat_comp_method}")
		print(f"- IDAT Additional flags/check bits: {idat_addit_flags}")
		print(f"- IDAT Compressed data blocks: {len(idat_comp_data)}")
		print(f"- IDAT Check value: {idat_check_value}")
		"""

		# try decompressing
		
	def decompress(self):
		idat = self.get_first_chunk(b"IDAT")

		self.decompressed_data = zlib.decompress(idat.data)

	def unfilter(self):
		data = self.decompressed_data # shorthand

		scanlines = []

		# skip each row
		# *3 is for 3 color bytes per pixel
		# +1 is for filter type byte prepending each line
		for i in range(0, len(data), self.width * 3 + 1):
			#print(data[i], i)
			scanlines.append(data[i:i + self.width * 3 + 1])
		
		#print(len(scanlines))

		# convert scanlines to array of decimal numbers
		for i in range(len(scanlines)):
			scanlines[i] = [x for x in scanlines[i]]
		
		## Now, unfilter data
		for i in range(len(scanlines)):
			line = scanlines[i]
			ftype = line[0]
			
			# Act on filter types
			# http://www.libpng.org/pub/png/spec/1.2/PNG-Filters.html
			if ftype == 0: # None
				# Data stays the same
				print(f"{i: >3}. None() row")
			if ftype == 1: # Sub
				# The Sub() filter transmits the difference between each
				# byte and the value of the corresponding byte of the prior 
				# pixel.
				bpp = 3
				print(f"{i: >3}. Sub() row")
				for x in range(1, len(line)):
					prev = 0
					if x - bpp > 0:
						prev = line[x - bpp]
					line[x] = (line[x] + prev) % 256
			if ftype == 2: # Up
				print(f"{i: >3}. Up() row")
				for x in range(1, len(line)):
					if i != 0: # don't want to do this on first line
						line[x] = (line[x] + scanlines[i - 1][x]) % 256
			if ftype == 3: # Average
				print(f"{i: >3}. Average() row")
				for x in range(1, len(line)):
					bpp = 3 # hardcoded
					prev = 0
					prior = 0
					if i != 0:
						prior = scanlines[i - 1][x]
					if x - bpp > 0:
						prev = line[x - bpp]
						
					line[x] = (line[x] + math.floor((prev + prior) / 2)) % 256
			if ftype == 4: # Paeth
				print(f"{i: >3}. Paeth() row")
			
			scanlines[i] = line
		
		self.scanlines = scanlines
	
	def log(self):
		print(f"Logging Image")
		print(f"  Width: {self.width}")
		print(f"  Height: {self.height}")
		print(f"  Bit depth: {self.bit_depth}")
		print(f"  Color type: {self.color_type}")
		print(f"  Compression method: {self.compression_method}")
		print(f"  Filter method: {self.filter_method}")
		print(f"  Interlace method: {self.interlace_method}")

with open("picture2.png", "br") as f:
	dat = f.read()

dat, magic_number = pull(dat, 8)

# create image
image = PNGImage()
image.read_from(dat)

for chunk in image.chunks:
	chunk.log()

# image.debug_data_log()
image.decompress()
image.unfilter()

# flush output before pygame
print("Starting pygame.", flush=True)

# start pygame and read image
if True:
	pygame.init()
	scale = 5

	win_width = image.width * scale
	win_height = image.height * scale
	surface = pygame.display.set_mode((win_width, win_height))
	pygame.display.set_caption("I know where you live")

	s = image.scanlines

	# get pixelarray
	#pxarr = pygame.PixelArray(surface)

	# you have to iterate by pygame coordinates so you can extract
	# color for each one
	for r in range(win_height):
		for c in range(win_width):
			# get coordinates in term of image
			ir = math.floor(r / scale)
			ic = math.floor(c / scale)

			# get color
			color = (
				s[ir][ic * 3 + 1],
				s[ir][ic * 3 + 2],
				s[ir][ic * 3 + 3]
			)

			# get shape
			shape = pygame.Rect(c, r, 1, 1)
			pygame.draw.rect(surface, color, shape)

	pygame.display.update()
	
	while True:
		for event in pygame.event.get():
			if event.type == pygame.QUIT:
				pygame.quit()
				sys.exit()

