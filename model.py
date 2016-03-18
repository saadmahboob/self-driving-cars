# -*- coding: utf-8 -*-
import numpy as np
import chainer, math, copy, os
from chainer import cuda, Variable, optimizers, serializers
from chainer import functions as F
from chainer import links as L
from activations import activations
from config import config

class FullyConnectedNetwork(chainer.Chain):
	def __init__(self, **layers):
		super(FullyConnectedNetwork, self).__init__(**layers)
		self.n_hidden_layers = 0
		self.activation_function = "elu"
		self.apply_batchnorm_to_input = False

	def forward_one_step(self, x, test):
		f = activations[self.activation_function]
		chain = [x]

		# Hidden layers
		for i in range(self.n_hidden_layers):
			u = getattr(self, "layer_%i" % i)(chain[-1])
			if self.apply_batchnorm:
				if i == 0 and self.apply_batchnorm_to_input is False:
					pass
				else:
					u = getattr(self, "batchnorm_%i" % i)(u, test=test)
			output = f(u)
			if self.apply_dropout:
				output = F.dropout(output, train=not test)
			chain.append(output)

		# Output
		u = getattr(self, "layer_%i" % self.n_hidden_layers)(chain[-1])
		if self.apply_batchnorm:
			u = getattr(self, "batchnorm_%i" % self.n_hidden_layers)(u, test=test)
		chain.append(f(u))

		return chain[-1]

	def __call__(self, x, test=False):
		return self.forward_one_step(x, test=test)

class Model:
	def __init__(self):
		self.exploration_rate = config.rl_initial_exploration

		# Replay Memory
		## (state, action, reward, next_state, episode_ends)
		shape_state = (config.rl_replay_memory_size, config.rl_history_length, 50)
		shape_action = (config.rl_replay_memory_size,)
		self.replay_memory = [
			np.zeros(shape_state, dtype=np.float32),
			np.zeros(shape_action, dtype=np.uint8),
			np.zeros(shape_action, dtype=np.int8),
			np.zeros(shape_state, dtype=np.float32)
		]
		self.total_replay_memory = 0

class DoubleDQN(Model):
	def __init__(self):
		Model.__init__(self)

		self.fc = self.build_network()
		self.load()
		self.update_target()

		self.optimizer_fc = optimizers.Adam(alpha=config.rl_learning_rate, beta1=config.rl_gradient_momentum)
		self.optimizer_fc.setup(self.fc)
		self.optimizer_fc.zero_grads()

	def build_network(self):
		config.check()
		wscale = config.q_wscale

		# Fully connected part of Q-Network
		fc_attributes = {}
		fc_units = [(50, config.q_fc_hidden_units[0])]
		fc_units += zip(config.q_fc_hidden_units[:-1], config.q_fc_hidden_units[1:])
		fc_units += [(config.q_fc_hidden_units[-1], len(config.actions))]

		for i, (n_in, n_out) in enumerate(fc_units):
			fc_attributes["layer_%i" % i] = L.Linear(n_in, n_out, wscale=wscale)
			fc_attributes["batchnorm_%i" % i] = L.BatchNormalization(n_out)

		fc = FullyConnectedNetwork(**fc_attributes)
		fc.n_hidden_layers = len(fc_units) - 1
		fc.activation_function = config.q_fc_activation_function
		fc.apply_batchnorm = config.apply_batchnorm
		fc.apply_dropout = config.q_fc_apply_dropout
		fc.apply_batchnorm_to_input = config.q_fc_apply_batchnorm_to_input
		if config.use_gpu:
			fc.to_gpu()

		return fc

	def eps_greedy(self, state, exploration_rate):
		prop = np.random.uniform()
		q_max = None
		q_min = None
		if prop < exploration_rate:
			action_index = np.random.randint(0, len(config.actions))
		else:
			state = Variable(state)
			if config.use_gpu:
				state.to_gpu()
			q = self.compute_q_variable(state, test=True)
			if config.use_gpu:
				action_index = cuda.to_cpu(cuda.cupy.argmax(q.data))
				q_max = cuda.to_cpu(cuda.cupy.max(q.data))
				q_min = cuda.to_cpu(cuda.cupy.min(q.data))
			else:
				action_index = np.argmax(q.data)
				q_max = np.max(q.data)
				q_min = np.min(q.data)

		action = self.get_action_with_index(action_index)
		return action, q_max, q_min

	def store_transition_in_replay_memory(self, state, action, reward, next_state):
		index = self.total_replay_memory % config.rl_replay_memory_size
		self.replay_memory[0][index] = state[0]
		self.replay_memory[1][index] = action
		self.replay_memory[2][index] = reward
		self.replay_memory[3][index] = next_state[0]
		self.total_replay_memory += 1

	def forward_one_step(self, state, action, reward, next_state, test=False):
		xp = cuda.cupy if config.use_gpu else np
		n_batch = state.shape[0]
		state = Variable(state)
		next_state = Variable(next_state)
		if config.use_gpu:
			state.to_gpu()
			next_state.to_gpu()
		q = self.compute_q_variable(state, test=test)
		q_ = self.compute_q_variable(next_state, test=test)
		max_action_indices = xp.argmax(q_.data, axis=1)
		if config.use_gpu:
			max_action_indices = cuda.to_cpu(max_action_indices)

		target_q = self.compute_target_q_variable(next_state, test=test)

		target = q.data.copy()

		for i in xrange(n_batch):
			max_action_index = max_action_indices[i]
			target_value = np.sign(reward[i]) + config.rl_discount_factor * target_q.data[i][max_action_indices[i]]
			action_index = self.get_index_with_action(action[i])
			old_value = target[i, action_index]
			diff = target_value - old_value
			if diff > 1.0:
				target_value = 1.0 + old_value	
			elif diff < -1.0:
				target_value = -1.0 + old_value	
			target[i, action_index] = target_value

		target = Variable(target)
		loss = F.mean_squared_error(target, q)
		return loss, q

	def replay_experience(self):
		if self.total_replay_memory == 0:
			return
		if self.total_replay_memory < config.rl_replay_memory_size:
			replay_index = np.random.randint(0, self.total_replay_memory, (config.rl_minibatch_size, 1))
		else:
			replay_index = np.random.randint(0, config.rl_replay_memory_size, (config.rl_minibatch_size, 1))

		shape_state = (config.rl_minibatch_size, config.rl_history_length, 50)
		shape_action = (config.rl_minibatch_size,)

		state = np.empty(shape_state, dtype=np.float32)
		action = np.empty(shape_action, dtype=np.uint8)
		reward = np.empty(shape_action, dtype=np.int8)
		next_state = np.empty(shape_state, dtype=np.float32)
		for i in xrange(config.rl_minibatch_size):
			state[i] = self.replay_memory[0][replay_index[i]]
			action[i] = self.replay_memory[1][replay_index[i]]
			reward[i] = self.replay_memory[2][replay_index[i]]
			next_state[i] = self.replay_memory[3][replay_index[i]]

		self.optimizer_fc.zero_grads()
		loss, _ = self.forward_one_step(state, action, reward, next_state, test=False)
		loss.backward()
		self.optimizer_fc.update()

	def compute_q_variable(self, state, test=False):
		return self.fc(state, test=test)

	def compute_target_q_variable(self, state, test=True):
		return self.target_fc(state, test=test)

	def update_target(self):
		self.target_fc = copy.deepcopy(self.fc)

	def get_action_with_index(self, i):
		return config.actions[i]

	def get_index_with_action(self, action):
		return config.actions.index(action)

	def decrease_exploration_rate(self):
		self.exploration_rate = max(self.exploration_rate - 1.0 / config.rl_final_exploration_frame, config.rl_final_exploration)

	def load(self):
		filename = "fc.model"
		if os.path.isfile(filename):
			serializers.load_hdf5(filename, self.fc)
			print "Loaded fully-connected network."

	def save(self):
		serializers.save_hdf5("fc.model", self.fc)
