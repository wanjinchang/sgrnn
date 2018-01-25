from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf
from tensorflow.python.util import nest


class SyntheticGradientRNN(object):
  def __init__(self):
    self._cell = None
    self._output_size = None
    self._num_unroll = None
    self._state_saver = None
    self._base_cell = None
    self._init_state = None
    self._cost = None

  @property
  def cost(self):
    return self._cost

  @property
  def cell(self):
    """
    This property needs to be overwritten by the child class
    and provide an implementation in terms of any subclass of RNNCell

    Returns:

    """
    if not self._cell:
      self._cell = tf.contrib.rnn.OutputProjectionWrapper(
        self.base_cell, self.output_size + self.total_state_size)
    return self._cell

  @property
  def base_cell(self):
    """Base cell without the output wrapper
    """
    raise NotImplementedError()

  @property
  def output_size(self):
    """size of output excluding synthetic gradient dimensions
    """
    return self._output_size

  @property
  def total_output_size(self):
    """size of output of rnn including synthetic gradient dimensions
    """
    return self.output_size + self.total_state_size

  @property
  def num_unroll(self):
    return self._num_unroll

  @property
  def state_saver(self):
    return self._state_saver

  @property
  def init_state(self):
    if not self._init_state:
      raise Exception("self._init_state needs to be defined during"
                      " graph construction time, using the initial"
                      " state from the state saving queue.")
    else:
      return self._init_state

  def build_synthetic_gradient_rnn(self, inputs, next_inputs, sequence_length):
    inputs = tf.unstack(inputs, num=self.num_unroll, axis=1)
    next_inputs = tf.unstack(next_inputs, num=self.num_unroll, axis=1)

    with tf.variable_scope('RNN') as scope:
      outputs, final_state = tf.nn.static_state_saving_rnn(
        cell=self.cell,
        inputs=inputs,
        state_saver=self.state_saver,
        state_name=self.state_name,
        sequence_length=sequence_length)

    with tf.variable_scope(scope, reuse=True):
      next_outputs, next_final_state = tf.nn.static_rnn(
        cell=self.cell,
        inputs=next_inputs,
        initial_state=final_state,
        sequence_length=sequence_length)

    synthetic_gradient = tf.slice(
      outputs[0], begin=[0, self.output_size], size=[-1, -1])
    synthetic_gradient = tf.split(
      synthetic_gradient, nest.flatten(self.state_size), axis=1)
    next_synthetic_gradient = tf.slice(
      next_outputs[0], begin=[0, self.output_size], size=[-1, -1])
    next_synthetic_gradient = tf.split(
      next_synthetic_gradient, nest.flatten(self.state_size), axis=1)

    with tf.variable_scope('logits'):
      stacked_outputs = tf.stack(outputs, axis=1)
      logits = tf.slice(stacked_outputs, begin=[0, 0, 0], size=[-1, -1, self.output_size])
    return logits, final_state, synthetic_gradient, next_synthetic_gradient

  @property
  def zero_state(self):
    """
    Returns:
      `list` of `Tensor` of [hidden_size] shape.
    """
    init_states = self.cell.zero_state(batch_size=1, dtype=tf.float32)
    init_states = nest.flatten(init_states)
    init_states = tuple([tf.squeeze(state, axis=0) for state in init_states])
    return init_states

  @property
  def init_state_dict(self):
    return {k:v for k, v in zip(
      nest.flatten(self.state_name), nest.flatten(self.zero_state))}

  @property
  def state_name(self):
    """
    Returns:
      nested `tuple` of `str`
    """
    i = 0

    def gen_state_name(zs):
      nonlocal i
      if isinstance(zs, tuple):
        return tuple([gen_state_name(s) for s in zs])
      else:
        name = 'state_{}'.format(i)
        i += 1
        return name
    return gen_state_name(self.state_size)

  @property
  def zero_initial_state_dict(self):
    """This property is used only for state saving queue
    Returns:
      `dict` where item is state_name:zero_state
    """
    return {k:v for k, v in zip(
      nest.flatten(self.state_name), nest.flatten(self.zero_state))}

  @property
  def state_size(self):
    return self.base_cell.state_size

  @property
  def total_state_size(self):
    state_sizes = nest.flatten(self.base_cell.state_size)
    return sum(state_sizes)


