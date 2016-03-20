# -*- coding: utf-8 -*-
import math, time
import numpy as np
from pprint import pprint
from vispy import app, gloo, visuals
from config import config

# 色
color_black = np.asarray((35, 35, 35, 255), dtype=np.float32) / 255.0
color_yellow = np.asarray((235, 163, 55, 255), dtype=np.float32) / 255.0
color_orange = np.asarray((247, 110, 0, 255), dtype=np.float32) / 255.0
color_red = np.asarray((217, 77, 76, 255), dtype=np.float32) / 255.0
color_blue = np.asarray((76, 179, 210, 255), dtype=np.float32) / 255.0
color_green = np.asarray((132, 172, 102, 255), dtype=np.float32) / 255.0
color_darkgreen = np.asarray((62, 96, 0, 255), dtype=np.float32) / 255.0
color_gray = np.asarray((47, 47, 45, 255), dtype=np.float32) / 255.0
color_whitesmoke = np.asarray((193, 193, 185, 255), dtype=np.float32) / 255.0
color_white = np.asarray((218, 217, 215, 255), dtype=np.float32) / 255.0

color_field_point = 0.6 * color_whitesmoke + 0.4 * color_gray

color_infographic_sensor_far = color_whitesmoke
color_infographic_sensor_mid = color_yellow
color_infographic_sensor_near = color_red
color_infographic_sensor_far_inactive = np.asarray((60, 60, 60, 255), dtype=np.float32) / 255.0
color_infographic_sensor_mid_inactive = np.asarray((63, 63, 63, 255), dtype=np.float32) / 255.0
color_infographic_sensor_near_inactive = np.asarray((69, 71, 70, 255), dtype=np.float32) / 255.0

color_car_normal = color_whitesmoke
color_car_crashed = color_red
color_car_reward = color_blue

field_point_vertex = """
attribute vec2 a_position;
attribute float a_point_size;

void main() {
	gl_Position = vec4(a_position, 0.0, 1.0);
	gl_PointSize = a_point_size;
}
"""

field_point_fragment = """
uniform vec4 u_color;

void main() {
	gl_FragColor = u_color;
}
"""

field_bg_vertex = """
attribute vec2 a_position;
attribute float a_is_wall;
varying float v_is_wall;

void main() {
	v_is_wall = a_is_wall;
	gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

field_bg_fragment = """
uniform vec4 u_bg_color;
uniform vec4 u_wall_color;
varying float v_is_wall;

void main() {
	gl_FragColor = mix(u_wall_color, u_bg_color, float(v_is_wall == 0));
}
"""

class Field:
	def __init__(self):
		self.enable_grid = True
		self.n_grid_h = 6
		self.n_grid_w = 8
		self.px = 80
		self.py = 80

		self.needs_display = True
		self.grid_subdiv_bg, self.grid_subdiv_wall = self.load()

		self.program_grid_point = gloo.Program(field_point_vertex, field_point_fragment)
		self.program_grid_point["u_color"] = color_field_point
		self.program_bg = gloo.Program(field_bg_vertex, field_bg_fragment)
		self.program_bg["u_bg_color"] = color_gray
		self.program_bg["u_wall_color"] = color_green

	def surrounding_wal_indicis(self, array_x, array_y, radius=1):
		start_xi = 0 if array_x - radius < 0 else array_x - radius
		start_yi = 0 if array_y - radius < 0 else array_y - radius
		end_xi = self.grid_subdiv_wall.shape[1] if array_x + radius + 1 > self.grid_subdiv_wall.shape[1] else array_x + radius + 1
		end_yi = self.grid_subdiv_wall.shape[0] if array_y + radius + 1 > self.grid_subdiv_wall.shape[0] else array_y + radius + 1
		zeros = np.zeros((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
		extract = self.grid_subdiv_wall[start_yi:end_yi, start_xi:end_xi]
		y_shift = max(radius - array_y, 0)
		x_shift = max(radius - array_x, 0)
		zeros[y_shift:y_shift + extract.shape[0], x_shift:x_shift + extract.shape[1]] = extract
		return  np.argwhere(zeros == 1)

	def set_needs_display(self):
		self.needs_display = True

	def load(self):
		# 背景
		grid_subdiv_bg = np.ones((self.n_grid_h * 4 + 4, self.n_grid_w * 4 + 4), dtype=np.uint8)

		# 壁
		grid_subdiv_wall = np.zeros((self.n_grid_h * 4 + 4, self.n_grid_w * 4 + 4), dtype=np.uint8)
		for x in xrange(grid_subdiv_wall.shape[1]):
			grid_subdiv_wall[0, x] = 1 if grid_subdiv_bg[0, x] == 1 else 0
			grid_subdiv_wall[-1, x] = 1 if grid_subdiv_bg[-1, x] == 1 else 0
			grid_subdiv_wall[1, x] = 1 if grid_subdiv_bg[1, x] == 1 else 0
			grid_subdiv_wall[-2, x] = 1 if grid_subdiv_bg[-2, x] == 1 else 0
		for y in xrange(grid_subdiv_wall.shape[0]):
			grid_subdiv_wall[y, 0] = 1 if grid_subdiv_bg[y, 0] == 1 else 0
			grid_subdiv_wall[y, -1] = 1 if grid_subdiv_bg[y, -1] == 1 else 0
			grid_subdiv_wall[y, 1] = 1 if grid_subdiv_bg[y, 1] == 1 else 0
			grid_subdiv_wall[y, -2] = 1 if grid_subdiv_bg[y, -2] == 1 else 0

		return grid_subdiv_bg, grid_subdiv_wall

	def is_screen_position_inside_field(self, pixel_x, pixel_y, grid_width=None, grid_height=None):
		if grid_width is None or grid_height is None:
			grid_width, grid_height = self.comput_grid_size()
		_, screen_height = gui.canvas.size
		subdivision_width = grid_width / float(self.n_grid_w) / 4.0
		subdivision_height = grid_height / float(self.n_grid_h) / 4.0
		if pixel_x < self.px - subdivision_width * 2:
			return False
		if pixel_x > self.px + grid_width + subdivision_width * 2:
			return False
		if pixel_y < screen_height - self.py - grid_height - subdivision_height * 2:
			return False
		if pixel_y > screen_height - self.py + subdivision_height * 2:
			return False
		return True

	def compute_array_index_from_position(self, pixel_x, pixel_y, grid_width=None, grid_height=None):
		grid_width, grid_height = self.comput_grid_size()
		if self.is_screen_position_inside_field(pixel_x, pixel_y, grid_width=grid_width, grid_height=grid_height) is False:
			return -1, -1
		_, screen_height = gui.canvas.size
		subdivision_width = grid_width / float(self.n_grid_w) / 4.0
		subdivision_height = grid_height / float(self.n_grid_h) / 4.0
		x = pixel_x - self.px + subdivision_width * 2
		y = pixel_y - (screen_height - self.py - grid_height - subdivision_height * 2)
		return int(x / subdivision_width), self.grid_subdiv_wall.shape[0] - int(y / subdivision_height) - 1

	def is_wall(self, array_x, array_y):
		if array_x < 0:
			return False
		if array_y < 0:
			return False
		if array_x >= self.grid_subdiv_wall.shape[1]:
			return False
		if array_y >= self.grid_subdiv_wall.shape[0]:
			return False
		return True if self.grid_subdiv_wall[array_y, array_x] == 1 else False


	def subdivision_exists(self, array_x, array_y):
		if array_x < 0:
			return False
		if array_y < 0:
			return False
		if array_x >= self.grid_subdiv_bg.shape[1]:
			return False
		if array_y >= self.grid_subdiv_bg.shape[0]:
			return False
		return True if self.grid_subdiv_bg[array_y, array_x] == 1 else False

	def comput_grid_size(self):
		sw, sh = gui.canvas.size
		ratio = self.n_grid_h / float(self.n_grid_w)
		if sw >= sh:
			lh = sh - self.py * 2
			lw = lh / ratio
			# フィールドは画面の左半分
			if lw > sw / 1.3 - self.px * 2:
				lw = sw / 1.3 - self.px * 2
				lh = lw * ratio
			if lh > sh - self.py * 2:
				lh = sh - self.py * 2
				lw = lh / ratio
		else:
			lw = sw / 1.3 - self.px * 2
			lh = lw * ratio
		return lw, lh

	def construct_wall_at_index(self, array_x, array_y):
		if array_x < 0:
			return
		if array_y < 0:
			return
		if array_x >= self.grid_subdiv_wall.shape[1]:
			return
		if array_y >= self.grid_subdiv_wall.shape[0]:
			return
		self.grid_subdiv_wall[array_y, array_x] = 1
		self.set_needs_display()

	def destroy_wall_at_index(self, array_x, array_y):
		if array_x < 2:
			return
		if array_y < 2:
			return
		if array_x >= self.grid_subdiv_wall.shape[1] - 2:
			return
		if array_y >= self.grid_subdiv_wall.shape[0] - 2:
			return
		self.grid_subdiv_wall[array_y, array_x] = 0
		self.set_needs_display()

	def set_positions(self):
		np.random.seed(0)
		sw, sh = gui.canvas.size
		lw ,lh = self.comput_grid_size()
		sgw = lw / float(self.n_grid_w) / 4.0 / float(sw) * 2.0
		sgh = lh / float(self.n_grid_h) / 4.0 / float(sh) * 2.0

		a_position = []
		a_point_size = []
		for nw in xrange(self.n_grid_w):
			x = lw / float(self.n_grid_w) * nw + self.px
			x = 2.0 * x / float(sw) - 1.0
			for nh in xrange(self.n_grid_h):
				y = lh / float(self.n_grid_h) * nh + self.py
				y = 2.0 * y / float(sh) - 1.0
				# 小さいグリッド
				for sub_y in xrange(5):
					_y = y + sgh * sub_y
					for sub_x in xrange(5):
						xi = nw * 4 + sub_x
						yi = nh * 4 + sub_y

						if self.subdivision_exists(xi, yi) or self.subdivision_exists(xi - 1, yi) or self.subdivision_exists(xi, yi - 1) or self.subdivision_exists(xi - 1, yi - 1):
							_x = x + sgw * sub_x
							# x, yそれぞれ2マス分ずらす
							a_position.append((_x, _y))
							if sub_x % 4 == 0 and sub_y % 4 == 0:
								a_point_size.append([3])
							else:
								a_point_size.append([1])

		self.program_grid_point["a_position"] = a_position
		self.program_grid_point["a_point_size"] = a_point_size

		bg_positions = []
		is_wall = []
		x_start = 2.0 * self.px / float(sw) - 1.0 - sgw * 2.0
		y_start = 2.0 * self.py / float(sh) - 1.0 - sgh * 2.0
		for h in xrange(self.grid_subdiv_bg.shape[0]):
			for w in xrange(self.grid_subdiv_bg.shape[1]):
				if self.grid_subdiv_bg[h, w] == 1:
					bg_positions.append((x_start + sgw * w, y_start + sgh * h))
					bg_positions.append((x_start + sgw * (w + 1), y_start + sgh * h))
					bg_positions.append((x_start + sgw * w, y_start + sgh * (h + 1)))

					bg_positions.append((x_start + sgw * (w + 1), y_start + sgh * h))
					bg_positions.append((x_start + sgw * w, y_start + sgh * (h + 1)))
					bg_positions.append((x_start + sgw * (w + 1), y_start + sgh * (h + 1)))

					for i in xrange(6):
						iw = 1.0 if self.grid_subdiv_wall[h, w] == 1 else 0.0
						is_wall.append(iw)

		np.random.seed(int(time.time()))
		self.program_bg["a_position"] = bg_positions
		self.program_bg["a_is_wall"] = np.asarray(is_wall, dtype=np.float32)

	def draw(self):
		if self.needs_display:
			self.needs_display = False
			self.set_positions()
		self.program_bg.draw("triangles")
		if self.enable_grid:
			self.program_grid_point.draw("points")

	def draw_wall(self):
		self.program_wall.draw("triangles")


infographic_sensor_vertex = """
attribute vec2 a_position;

void main() {
	gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

infographic_sensor_fragment = """
uniform vec2 u_center;
uniform vec2 u_size;
uniform float u_near[8];
uniform float u_mid[16];
uniform float u_far[24];
uniform vec4 u_near_color;
uniform vec4 u_mid_color;
uniform vec4 u_far_color;
uniform vec4 u_near_color_inactive;
uniform vec4 u_mid_color_inactive;
uniform vec4 u_far_color_inactive;
uniform vec4 u_line_color;

const float M_PI = 3.14159265358979323846;

float atan2(in float y, in float x)
{
	float result = atan(y, x) + M_PI;
	return 1.0 - mod(result + M_PI / 2.0, M_PI * 2.0) / M_PI / 2.0;
}

void main() {
	vec2 coord = gl_FragCoord.xy;
	float d = distance(coord, u_center);
	vec2 local = coord - u_center;
	float rad = atan2(local.y, local.x);

	// #1
	float line_width = 1;
	float radius = u_size.x / 2.0 * 0.7;
	float diff = d - radius;
	if(abs(diff) <= line_width){
		diff /= line_width;
		gl_FragColor = mix(vec4(u_line_color.rgb, fract(1 + diff)), vec4(u_line_color.rgb, 1.0 - fract(diff)), float(diff > 0));
		return;
	}

	// far
	radius = u_size.x / 2.0 * 0.6;
	diff = d - radius;
	line_width = 10;
	float segments = 24.0;
	if(abs(diff) <= line_width / 2.0){
		vec4 result;
		if(diff >= 0){
			diff -= (line_width / 2.0 - 1.0);
			result = mix(vec4(u_far_color.rgb, 1.0 - fract(diff)), u_far_color, float(diff < 0));
		}else{
			diff += line_width / 2.0;
			result = mix(vec4(u_far_color.rgb, fract(1 + diff)), u_far_color, float(diff >= 1));
		}
		int index = int(fract(rad + 1.0 / segments / 2.0) * segments);
		float rat = u_far[index];
		gl_FragColor = mix(vec4(u_far_color_inactive.rgb, result.a), result, rat);
		return;
	}

	// mid
	radius = u_size.x / 2.0 * 0.5;
	diff = d - radius;
	line_width = 10;
	segments = 16.0;
	if(abs(diff) <= line_width / 2.0){
		vec4 result;
		if(diff >= 0){
			diff -= (line_width / 2.0 - 1.0);
			result = mix(vec4(u_mid_color.rgb, 1.0 - fract(diff)), u_mid_color, float(diff < 0));
		}else{
			diff += line_width / 2.0;
			result = mix(vec4(u_mid_color.rgb, fract(1 + diff)), u_mid_color, float(diff >= 1));
		}
		int index = int(fract(rad + 1.0 / segments / 2.0) * segments);
		float rat = u_mid[index];
		gl_FragColor = mix(vec4(u_mid_color_inactive.rgb, result.a), result, rat);
		return;
	}

	// near
	radius = u_size.x / 2.0 * 0.4;
	diff = d - radius;
	line_width = 10;
	segments = 8.0;
	if(abs(diff) <= line_width / 2.0){
		vec4 result;
		if(diff >= 0){
			diff -= (line_width / 2.0 - 1.0);
			result = mix(vec4(u_near_color.rgb, 1.0 - fract(diff)), u_near_color, float(diff < 0));
		}else{
			diff += line_width / 2.0;
			result = mix(vec4(u_near_color.rgb, fract(1 + diff)), u_near_color, float(diff >= 1));
		}
		int index = int(fract(rad + 1.0 / segments / 2.0) * segments);
		float rat = u_near[index];
		gl_FragColor = mix(vec4(u_near_color_inactive.rgb, result.a), result, rat);
		return;
	}

}
"""

class Infographic():
	def __init__(self):
		self.program_sensor = gloo.Program(infographic_sensor_vertex, infographic_sensor_fragment)
		self.program_sensor["u_near_color"] = color_infographic_sensor_near
		self.program_sensor["u_mid_color"] = color_infographic_sensor_mid
		self.program_sensor["u_far_color"] = color_infographic_sensor_far
		self.program_sensor["u_near_color_inactive"] = color_infographic_sensor_near_inactive
		self.program_sensor["u_mid_color_inactive"] = color_infographic_sensor_mid_inactive
		self.program_sensor["u_far_color_inactive"] = color_infographic_sensor_far_inactive
		self.program_sensor["u_line_color"] = color_whitesmoke

		self.color_hex_str_text = "#c1c1b9"

		self.text_title_field = visuals.TextVisual("SELF-DRIVING CARS", color=self.color_hex_str_text, bold=True, anchor_x="left", anchor_y="top")
		self.text_title_field.font_size = 16

		self.text_title_data = visuals.TextVisual("DATA STREAM", color=self.color_hex_str_text, bold=True, anchor_x="left", anchor_y="top")
		self.text_title_data.font_size = 16

		self.text_title_sensor = visuals.TextVisual("SENSOR", color=self.color_hex_str_text, bold=True, anchor_x="left", anchor_y="top")
		self.text_title_sensor.font_size = 16

	def set_positions(self):
		sw, sh = gui.canvas.size
		sw = float(sw)
		sh = float(sh)
		lw ,lh = gui.field.comput_grid_size()
		sgw = lw / float(gui.field.n_grid_w) / 4.0
		sgh = lh / float(gui.field.n_grid_h) / 4.0

		# Text
		self.text_title_field.pos = gui.field.px - sgw * 1.5, sh - lh - gui.field.py - sgh * 3.5
		self.text_title_data.pos = gui.field.px + lw + sgw * 3.5, sh - lh - gui.field.py - sgh * 3.5
		self.text_title_sensor.pos = gui.field.px + lw + sgw * 3.5, sh - gui.field.py - sgh * 8.5

	def configure(self, canvas, viewport):
		self.text_title_field.transforms.configure(canvas=canvas, viewport=viewport)
		self.text_title_data.transforms.configure(canvas=canvas, viewport=viewport)
		self.text_title_sensor.transforms.configure(canvas=canvas, viewport=viewport)
		
	def draw(self):
		self.set_positions()
		self.text_title_field.draw()
		self.text_title_data.draw()
		self.text_title_sensor.draw()
		self.draw_sensor()

	def draw_sensor(self):
		car = controller.get_car_at_index(0)
		sensor_value = car.get_sensor_value()
		# HACK
		for i in xrange(8):
			self.program_sensor["u_near[%d]" % i] = sensor_value[i]
		for i in xrange(16):
			self.program_sensor["u_mid[%d]" % i] = sensor_value[i + 8]
		for i in xrange(24):
			self.program_sensor["u_far[%d]" % i] = sensor_value[i + 24]

		sw, sh = gui.canvas.size
		sw = float(sw)
		sh = float(sh)
		lw ,lh = gui.field.comput_grid_size()
		sgw = lw / float(gui.field.n_grid_w) / 4.0
		sgh = lh / float(gui.field.n_grid_h) / 4.0
		base_x = 2.0 * (gui.field.px + lw + sgw * 3.0) / sw - 1
		base_y = 2.0 * (gui.field.py - sgh * 2.0) / sh - 1
		width = sgw * 10 / sw * 2.0
		height = sgh * 10 / sh * 2.0
		center = (gui.field.px + lw + sgw * 8.0, gui.field.py + sgh * 3.0)
		self.program_sensor["u_center"] = center
		self.program_sensor["u_size"] = sgw * 10, sgh * 10
		positions = []
		positions.append((base_x, base_y))
		positions.append((base_x + width, base_y))
		positions.append((base_x, base_y + height))
		positions.append((base_x + width, base_y + height))
		positions.append(positions[1])
		positions.append(positions[2])
		positions.append(positions[3])
		self.program_sensor["a_position"] = positions

		self.program_sensor.draw("triangles")

controller_cars_vertex = """
attribute vec2 a_position;
attribute vec4 a_color;
varying vec4 v_color;

void main() {
	v_color = a_color;
	gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

controller_cars_fragment = """
varying vec4 v_color;

void main() {
	gl_FragColor = v_color;
}
"""
controller_location_vertex = """
attribute vec2 a_position;

void main() {
	gl_Position = vec4(a_position, 0.0, 1.0);
}
"""

controller_location_fragment = """
uniform vec2 u_center;
uniform vec2 u_size;
uniform vec4 u_line_color;

void main() {
	vec2 coord = gl_FragCoord.xy;
	float d = distance(coord, u_center);
	float line_width = 1;
	float radius = u_size.x / 2.0 * 0.8;
	float diff = d - radius;
	if(abs(diff) <= line_width){
		diff /= line_width;
		gl_FragColor = mix(vec4(u_line_color.rgb, fract(1 + diff)), vec4(u_line_color.rgb, 1.0 - fract(diff)), float(diff > 0));
		return;
	}
}
"""

class Controller:
	ACTION_NO_OPS = 0
	ACTION_THROTTLE = 1
	ACTION_BRAKE = 2
	ACTION_STEER_RIGHT = 3
	ACTION_STEER_LEFT = 4
	def __init__(self):
		self.cars = []
		self.lookup = np.zeros((gui.field.n_grid_h * 4 + 4, gui.field.n_grid_w * 4 + 4, config.initial_num_car), dtype=np.uint8)
		self.program_cars = gloo.Program(controller_cars_vertex, controller_cars_fragment)
		self.program_location = gloo.Program(controller_location_vertex, controller_location_fragment)
		self.program_location["u_line_color"] = color_yellow
		self.textvisuals = []
		self.glue = None
		for i in xrange(config.initial_num_car):
			self.cars.append(Car(self, index=i))
			text = visuals.TextVisual("car %d" % i, color="white", anchor_x="left", anchor_y="top")
			text.font_size = 8
			self.textvisuals.append(text)

	def configure(self, canvas, viewport):
		for text in self.textvisuals:
			text.transforms.configure(canvas=canvas, viewport=viewport)

	def draw(self):
		positions = []
		colors = []
		for car in self.cars:
			p, c = car.compute_gl_attributes()
			positions.extend(p)
			colors.extend(c)
		self.program_cars["a_position"] = positions
		self.program_cars["a_color"] = colors
		self.program_cars.draw("lines")
		for text in self.textvisuals:
			text.draw()

		sw = float(gui.canvas.size[0])
		sh = float(gui.canvas.size[1])
		length = gui.canvas.size[0] / 10.0
		location_width = length / sw * 2.0
		location_height = length / sh * 2.0
		car = self.get_car_at_index(0)
		location_center = 2.0 * (car.pos[0] / sw) - 1, 2.0 - 2.0 * (car.pos[1] / sh)  - 1
		location_positions = [(location_center[0] - location_width / 2.0, location_center[1] - location_height / 2.0),
								(location_center[0] + location_width / 2.0, location_center[1] - location_height / 2.0),
								(location_center[0] - location_width / 2.0, location_center[1] + location_height / 2.0),
								(location_center[0] + location_width / 2.0, location_center[1] + location_height / 2.0)]
		a_position = []
		a_position.append(location_positions[0])
		a_position.append(location_positions[1])
		a_position.append(location_positions[2])
		a_position.append(location_positions[3])
		self.program_location["u_center"] = car.pos[0], sh - car.pos[1]
		self.program_location["u_size"] = length, length
		self.program_location["a_position"] = a_position
		self.program_location.draw("triangle_strip")

	def step(self):
		if self.glue is None:
			return
		for car in self.cars:
			state = car.rl_state
			action = self.glue.take_action(car_index=car.index)
			if action == Controller.ACTION_NO_OPS:
				pass
			elif action == Controller.ACTION_THROTTLE:
				car.action_throttle()
			elif action == Controller.ACTION_BRAKE:
				car.action_brake()
			elif action == Controller.ACTION_STEER_RIGHT:
				car.action_steer_right()
			elif action == Controller.ACTION_STEER_LEFT:
				car.action_steer_left()
			else:
				raise NotImplementedError()
			car.move()
			new_state, reward = car.get_rl_state_and_reward()
			if new_state is not None and state is not None:
				self.glue.agent_step(action, reward, new_state, car_index=car.index)
			text = self.textvisuals[car.index]
			text.pos = car.pos[0] + 10, car.pos[1] - 10

	def find_near_cars(self, array_x, array_y, radius=1):
		start_xi = 0 if array_x - radius < 0 else array_x - radius
		start_yi = 0 if array_y - radius < 0 else array_y - radius
		end_xi = self.lookup.shape[1] if array_x + radius + 1 > self.lookup.shape[1] else array_x + radius + 1
		end_yi = self.lookup.shape[0] if array_y + radius + 1 > self.lookup.shape[0] else array_y + radius + 1
		return np.argwhere(self.lookup[start_yi:end_yi, start_xi:end_xi, :] == 1)

	def get_car_at_index(self, index=0):
		if index < len(self.cars):
			return self.cars[index]
		return None

class Car:
	lookup = np.array([[39, 38, 37, 36, 35, 34, 33], [40, 18, 17, 16, 15, 14, 32], [41, 19, 5, 4, 3, 13, 31], [42, 20, 6, -1, 2, 12, 30], [43, 21, 7, 0, 1, 11, 29], [44, 22, 23, 8, 9, 10, 28], [45, 46, 47, 24, 25, 26, 27]])
	car_width = 12.0
	car_height = 20.0
	shape = [(-car_width/2.0, car_height/2.0), (car_width/2.0, car_height/2.0),(car_width/2.0, car_height/2.0), (car_width/2.0, -car_height/2.0),(car_width/2.0, -car_height/2.0), (-car_width/2.0, -car_height/2.0),(-car_width/2.0, -car_height/2.0), (-car_width/2.0, car_height/2.0),(0.0, car_height/2.0+1.0), (0.0, 1.0)]
	max_speed = 10
	STATE_NORMAL = 0
	STATE_REWARD = 1
	STATE_CRASHED = 2
	def __init__(self, manager, index=0):
		self.index = index
		self.manager = manager
		self.speed = 0
		self.steering = 0
		self.steering_unit = math.pi / 30.0
		self.state_code = Car.STATE_NORMAL
		self.pos = (gui.canvas.size[0] / 2.0 + np.random.randint(400) - 200, gui.canvas.size[1] / 2.0 + np.random.randint(400) - 200)
		self.prev_lookup_xi, self.prev_lookup_yi = gui.field.compute_array_index_from_position(self.pos[0], self.pos[1])
		self.manager.lookup[self.prev_lookup_yi, self.prev_lookup_xi, self.index] = 1
		self.over = False
		self.rl_state = None

	def compute_gl_attributes(self):
		xi, yi = gui.field.compute_array_index_from_position(self.pos[0], self.pos[1])
		sw, sh = gui.canvas.size
		cos = math.cos(-self.steering)
		sin = math.sin(-self.steering)
		positions = []
		colors = []
		for x, y in Car.shape:
			_x = 2.0 * (x * cos - y * sin + self.pos[0]) / sw - 1
			_y = 2.0 * (x * sin + y * cos + (sh - self.pos[1])) / sh - 1
			positions.append((_x, _y))
			if self.state_code == Car.STATE_CRASHED:
				colors.append(color_car_crashed)
			elif self.state_code == Car.STATE_REWARD:
				colors.append(color_car_reward)
			else:
				colors.append(color_car_normal)
		return positions, colors

	def respawn(self):
		self.pos = (gui.canvas.size[0] / 2.0, gui.canvas.size[1] / 2.0)

	def get_sensor_value(self):
		# 衝突判定
		sw, sh = gui.canvas.size
		xi, yi = gui.field.compute_array_index_from_position(self.pos[0], self.pos[1])
		values = np.zeros((48,), dtype=np.float32)
		self.over == False

		# 壁
		blocks = gui.field.surrounding_wal_indicis(xi, yi, 3)
		for block in blocks:
			i = Car.lookup[block[0]][block[1]]
			if i != -1:
				values[i] = 1.0

		# 他の車
		near_cars = self.manager.find_near_cars(xi, yi, 3)
		for _, __, car_index in near_cars:
			if car_index == self.index:
				continue
			target_car = self.manager.get_car_at_index(car_index)
			if target_car is None:
				continue
			direction = target_car.pos[0] - self.pos[0], target_car.pos[1] - self.pos[1]
			distance = math.sqrt(direction[0] ** 2 + direction[1] ** 2) / float(sw)
			theta = (math.atan2(direction[1], direction[0]) + math.pi / 2.0) % (math.pi * 2.0)
			ds = 0.018
			dsi = int(distance / ds)
			if dsi <= 1:
				if dsi == 0:
					self.over == True
				values[int(theta / math.pi * 4.0)] = 1
			elif dsi == 2:
				values[int(theta / math.pi * 8.0) + 8] = 1
			elif dsi == 3:
				values[int(theta / math.pi * 12.0) + 24] = 1

		# 車体の向きに合わせる
		area = int(self.steering / math.pi * 4.0)
		ratio = self.steering % (math.pi / 4.0)
		mix = np.roll(values[0:8], -(area + 1)) * ratio + np.roll(values[0:8], -area) * (1.0 - ratio)
		values[0:8] = mix

		area = int(self.steering / math.pi * 8.0)
		ratio = self.steering % (math.pi / 8.0)
		mix = np.roll(values[8:24], -(area + 1)) * ratio + np.roll(values[8:24], -area) * (1.0 - ratio)
		values[8:24] = mix

		area = int(self.steering / math.pi * 12.0)
		ratio = self.steering % (math.pi / 12.0)
		mix = np.roll(values[24:48], -(area + 1)) * ratio + np.roll(values[24:48], -area) * (1.0 - ratio)
		values[24:48] = mix

		return values

	def get_rl_state_and_reward(self):
		reward = max(self.speed / float(self.max_speed), 0.0)
		if self.state_code == Car.STATE_CRASHED:
			reward = -1.0
		return self.rl_state, reward

	def move(self):
		cos = math.cos(-self.steering)
		sin = math.sin(-self.steering)
		x = -sin * self.speed		
		y = cos * self.speed
		sensors = self.get_sensor_value()

		rl_state = np.empty((50,), dtype=np.float32)
		rl_state[0:48] = sensors
		rl_state[48] = self.speed / float(self.max_speed)
		rl_state[49] = self.steering / math.pi / 2.0
		self.rl_state = rl_state

		self.state_code = Car.STATE_NORMAL
		if sensors[0] > 0.7 and self.speed > 0:
			self.speed = 0
			self.state_code = Car.STATE_CRASHED
			return
		if sensors[4] > 0.7 and self.speed < 0:
			self.speed = 0
			self.state_code = Car.STATE_CRASHED
			return
		if self.speed > 0:
			self.state_code = Car.STATE_REWARD
		if self.over:
			self.state_code = Car.STATE_CRASHED
		self.pos = (self.pos[0] + x, self.pos[1] - y)
		if gui.field.is_screen_position_inside_field(self.pos[0], self.pos[1]) is False:
			self.respawn()

		xi, yi = gui.field.compute_array_index_from_position(self.pos[0], self.pos[1])
		if xi == self.prev_lookup_xi and yi == self.prev_lookup_yi:
			return
		self.manager.lookup[self.prev_lookup_yi,self.prev_lookup_xi,self.index] = 0
		self.manager.lookup[yi, xi, self.index] = 1
		self.prev_lookup_xi = xi
		self.prev_lookup_yi = yi

	# アクセル
	def action_throttle(self):
		self.speed = min(self.speed + 1, self.max_speed)

	# ブレーキ
	def action_brake(self):
		self.speed = max(self.speed - 1, -self.max_speed)

	# ハンドル
	def action_steer_right(self):
		if self.speed > 0:
			self.steering = (self.steering + self.steering_unit) % (math.pi * 2.0)
		elif self.speed < 0:
			self.steering = (self.steering - self.steering_unit) % (math.pi * 2.0)

	def action_steer_left(self):
		if self.speed > 0:
			self.steering = (self.steering - self.steering_unit) % (math.pi * 2.0)
		elif self.speed < 0:
			self.steering = (self.steering + self.steering_unit) % (math.pi * 2.0)

class Canvas(app.Canvas):
	def __init__(self):
		app.Canvas.__init__(self, size=config.screen_size, title="self-driving", keys="interactive")

		self.is_mouse_pressed = False
		self.is_key_shift_pressed = False

		self._timer = app.Timer(1.0 / 20.0, connect=self.on_timer, start=True)

	def step(self):
		pass

	def on_draw(self, event):
		gloo.clear(color="#2e302f")
		gloo.set_viewport(0, 0, *self.physical_size)
		gui.field.draw()
		gui.infographic.draw()
		controller.draw()

	def on_resize(self, event):
		self.activate_zoom()
		print "#on_resize()", (self.width, self.height)

	def on_mouse_press(self, event):
		self.is_mouse_pressed = True
		self.toggle_wall(event.pos)

	def on_mouse_release(self, event):
		self.is_mouse_pressed = False

	def on_mouse_move(self, event):
		self.toggle_wall(event.pos)
		# car = controller.get_car_at_index(0)
		# car.pos = event.pos[0], event.pos[1]

	def on_mouse_wheel(self, event):
		# car = controller.get_car_at_index(0)
		# car.action_steer_right()
		pass

	def toggle_wall(self, pos):
		if self.is_mouse_pressed:
			if gui.field.is_screen_position_inside_field(pos[0], pos[1]):
				x, y = gui.field.compute_array_index_from_position(pos[0], pos[1])
				if self.is_key_shift_pressed:
					gui.field.destroy_wall_at_index(x, y)
				else:
					gui.field.construct_wall_at_index(x, y)

	def on_key_press(self, event):
		if event.key == "Shift":
			self.is_key_shift_pressed = True

	def on_key_release(self, event):
		if event.key == "Shift":
			self.is_key_shift_pressed = False

	def activate_zoom(self):
		self.width, self.height = self.size
		gloo.set_viewport(0, 0, *self.physical_size)
		vp = (0, 0, self.physical_size[0], self.physical_size[1])
		gui.infographic.configure(canvas=self, viewport=vp)
		controller.configure(canvas=self, viewport=vp)
		gui.field.set_needs_display()
		
	def on_timer(self, event):
		controller.step()
		self.update()

class Gui:
	def __init__(self):
		self.canvas = Canvas()
		self.infographic = Infographic()
		self.field = Field()
		# gui.canvas.measure_fps()

gui = Gui()
controller = Controller()