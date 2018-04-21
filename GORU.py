"""
Module implementing GORU Cell.
"""
import tensorflow as tf
import numpy as np
from tensorflow.python.ops import variable_scope as vs
from tensorflow.python.ops.rnn_cell_impl import RNNCell


def modrelu(z, b):

    z_norm = tf.abs(z) + 0.00001
    step1 = z_norm + b
    step2 = tf.nn.relu(step1)
    step3 = tf.sign(z)

    return tf.multiply(step3, step2)


def _eunn_param(hidden_size, capacity=2, fft=False):
    """
    Create parameters and do the initial preparations
    """
    theta_phi_initializer = tf.random_uniform_initializer(-np.pi, np.pi)
    if fft:
        capacity = int(np.ceil(np.log2(hidden_size)))

        diag_list_0 = []
        off_list_0 = []
        varsize = 0
        for i in range(capacity):
            size = capacity - i
            normal_size = (hidden_size // (2 ** size)) * (2 ** (size - 1))
            extra_size = max(0, (hidden_size %
                                 (2 ** size)) - (2 ** (size - 1)))
            varsize += normal_size + extra_size

        params_theta = vs.get_variable(
            "theta_0", [varsize], initializer=theta_phi_initializer)
        cos_theta = tf.cos(params_theta)
        sin_theta = tf.sin(params_theta)

        last = 0
        for i in range(capacity):
            size = capacity - i
            normal_size = (hidden_size // (2 ** size)) * (2 ** (size - 1))
            extra_size = max(0, (hidden_size %
                                 (2 ** size)) - (2 ** (size - 1)))

            cos_list_normal = tf.slice(cos_theta, [last], [normal_size])
            cos_list_normal = tf.concat([cos_list_normal, cos_list_normal], 0)
            cos_list_extra = tf.slice(
                cos_theta, [last + normal_size], [extra_size])
            cos_list_extra = tf.concat([cos_list_extra, tf.ones(
                [hidden_size - 2 * normal_size - 2 * extra_size]),
                cos_list_extra], 0)

            sin_list_normal = tf.slice(sin_theta, [last], [normal_size])
            sin_list_normal = tf.concat([sin_list_normal, -sin_list_normal], 0)
            sin_list_extra = tf.slice(
                sin_theta, [last + normal_size], [extra_size])
            sin_list_extra = tf.concat([sin_list_extra, tf.zeros(
                [hidden_size - 2 * normal_size - 2 * extra_size]),
                -sin_list_extra], 0)

            last += normal_size + extra_size

            if normal_size != 0:
                cos_list_normal = tf.reshape(tf.transpose(tf.reshape(
                    cos_list_normal, [-1, 2 * normal_size // (2**size)])),
                    [-1])
                sin_list_normal = tf.reshape(tf.transpose(tf.reshape(
                    sin_list_normal, [-1, 2 * normal_size // (2**size)])),
                    [-1])

            cos_list = tf.concat([cos_list_normal, cos_list_extra], 0)
            sin_list = tf.concat([sin_list_normal, sin_list_extra], 0)
            diag_list_0.append(cos_list)
            off_list_0.append(sin_list)

        diag_vec = tf.stack(diag_list_0, 0)
        off_vec = tf.stack(off_list_0, 0)

    else:
        capacity_b = capacity // 2
        capacity_a = capacity - capacity_b

        hidden_size_a = hidden_size // 2
        hidden_size_b = (hidden_size - 1) // 2

        params_theta_0 = vs.get_variable(
            "theta_0", [capacity_a, hidden_size_a],
            initializer=theta_phi_initializer)
        cos_theta_0 = tf.reshape(tf.cos(params_theta_0), [capacity_a, -1, 1])
        sin_theta_0 = tf.reshape(tf.sin(params_theta_0), [capacity_a, -1, 1])

        params_theta_1 = vs.get_variable(
            "theta_1", [capacity_b, hidden_size_b],
            initializer=theta_phi_initializer)
        cos_theta_1 = tf.reshape(tf.cos(params_theta_1), [capacity_b, -1, 1])
        sin_theta_1 = tf.reshape(tf.sin(params_theta_1), [capacity_b, -1, 1])

        cos_list_0 = tf.reshape(
            tf.concat([cos_theta_0, cos_theta_0], 2), [capacity_a, -1])
        sin_list_0 = tf.reshape(
            tf.concat([sin_theta_0, -sin_theta_0], 2), [capacity_a, -1])
        if hidden_size_a * 2 != hidden_size:
            cos_list_0 = tf.concat([cos_list_0, tf.ones([capacity_a, 1])], 1)
            sin_list_0 = tf.concat([sin_list_0, tf.zeros([capacity_a, 1])], 1)

        cos_list_1 = tf.reshape(
            tf.concat([cos_theta_1, cos_theta_1], 2), [capacity_b, -1])
        cos_list_1 = tf.concat([tf.ones((capacity_b, 1)), cos_list_1], 1)
        sin_list_1 = tf.reshape(
            tf.concat([sin_theta_1, -sin_theta_1], 2), [capacity_b, -1])
        sin_list_1 = tf.concat([tf.zeros((capacity_b, 1)), sin_list_1], 1)
        if hidden_size_b * 2 != hidden_size - 1:
            cos_list_1 = tf.concat([cos_list_1, tf.zeros([capacity_b, 1])], 1)
            sin_list_1 = tf.concat([sin_list_1, tf.zeros([capacity_b, 1])], 1)

        if capacity_b != capacity_a:

            cos_list_1 = tf.concat([cos_list_1, tf.zeros([1, hidden_size])], 0)
            sin_list_1 = tf.concat([sin_list_1, tf.zeros([1, hidden_size])], 0)

        diag_vec = tf.reshape(tf.concat([cos_list_0, cos_list_1], 1), [
                              capacity_a * 2, hidden_size])
        off_vec = tf.reshape(tf.concat([sin_list_0, sin_list_1], 1), [
                             capacity_a * 2, hidden_size])

        if capacity_b != capacity_a:
            diag_vec = tf.slice(diag_vec, [0, 0], [capacity, hidden_size])
            off_vec = tf.slice(off_vec, [0, 0], [capacity, hidden_size])

    def _toTensorArray(elems):

        elems = tf.convert_to_tensor(elems)
        n = tf.shape(elems)[0]
        elems_ta = tf.TensorArray(
            dtype=elems.dtype, size=n, dynamic_size=False,
            infer_shape=True, clear_after_read=False)
        elems_ta = elems_ta.unstack(elems)
        return elems_ta

    diag_vec = _toTensorArray(diag_vec)
    off_vec = _toTensorArray(off_vec)

    diag = None

    return diag_vec, off_vec, diag, capacity


def _eunn_loop(state, capacity, diag_vec_list, off_vec_list, diag, fft):
    """
    EUNN main loop, applying unitary matrix on input tensor
    """
    i = 0

    def layer_tunable(x, i):

        diag_vec = diag_vec_list.read(i)
        off_vec = off_vec_list.read(i)

        diag = tf.multiply(x, diag_vec)
        off = tf.multiply(x, off_vec)

        def even_input(off, size):

            def even_s(off, size):
                off = tf.reshape(off, [-1, size // 2, 2])
                off = tf.reshape(tf.reverse(off, [2]), [-1, size])
                return off

            def odd_s(off, size):
                off, helper = tf.split(off, [size - 1, 1], 1)
                size -= 1
                off = even_s(off, size)
                off = tf.concat([off, helper], 1)
                return off

            off = tf.cond(tf.equal(tf.mod(size, 2), 0), lambda: even_s(
                off, size), lambda: odd_s(off, size))
            return off

        def odd_input(off, size):
            helper, off = tf.split(off, [1, size - 1], 1)
            size -= 1
            off = even_input(off, size)
            off = tf.concat([helper, off], 1)
            return off

        size = int(off.get_shape()[1])
        off = tf.cond(tf.equal(tf.mod(i, 2), 0), lambda: even_input(
            off, size), lambda: odd_input(off, size))

        layer_output = diag + off
        i += 1

        return layer_output, i

    def layer_fft(state, i):

        diag_vec = diag_vec_list.read(i)
        off_vec = off_vec_list.read(i)
        diag = tf.multiply(state, diag_vec)
        off = tf.multiply(state, off_vec)

        hidden_size = int(off.get_shape()[1])
        # size = 2**i
        dist = capacity - i
        normal_size = (hidden_size // (2**dist)) * (2**(dist - 1))
        normal_size *= 2
        extra_size = tf.maximum(0, (hidden_size % (2**dist)) - (2**(dist - 1)))
        hidden_size -= normal_size

        def modify(off_normal, dist, normal_size):
            off_normal = tf.reshape(tf.reverse(tf.reshape(
                off_normal,
                [-1, normal_size // (2**dist), 2, (2**(dist - 1))]), [2]),
                [-1, normal_size])
            return off_normal

        def do_nothing(off_normal):
            return off_normal

        off_normal, off_extra = tf.split(off, [normal_size, hidden_size], 1)
        off_normal = tf.cond(tf.equal(normal_size, 0), lambda: do_nothing(
            off_normal), lambda: modify(off_normal, dist, normal_size))
        helper1, helper2 = tf.split(
            off_extra, [hidden_size - extra_size, extra_size], 1)
        off_extra = tf.concat([helper2, helper1], 1)
        off = tf.concat([off_normal, off_extra], 1)

        layer_output = diag + off
        i += 1

        return layer_output, i

    if fft:
        layer_function = layer_fft
    else:
        layer_function = layer_tunable
    output, _ = tf.while_loop(lambda state, i: tf.less(
        i, capacity), layer_function, [state, i])

    if not (diag is None):
        output = tf.multiply(output, diag)

    return output


class GORUCell(RNNCell):
    """
    Gated Orthogonal Recurrent Unit Cell
    The implementation is based on: http://arxiv.org/abs/1706.02761.
    """

    def __init__(self, hidden_size, capacity=2, fft=True, activation=modrelu):
        super(GORUCell, self).__init__()
        self._hidden_size = hidden_size
        self._activation = activation
        self._capacity = capacity
        self._fft = fft

        self.diag_vec, self.off_vec, self.diag, self._capacity = _eunn_param(
            hidden_size, capacity, fft)

    @property
    def state_size(self):
        return self._hidden_size

    @property
    def output_size(self):
        return self._hidden_size

    @property
    def capacity(self):
        return self._capacity

    def __call__(self, inputs, state, scope=None):
        with vs.variable_scope(scope or "goru_cell"):

            U_init = tf.random_uniform_initializer(-0.01, 0.01)
            b_init = tf.constant_initializer(2.)
            mod_b_init = tf.constant_initializer(0.01)

            U = vs.get_variable(
                "U", [inputs.get_shape()[-1], self._hidden_size * 3],
                dtype=tf.float32, initializer=U_init)
            Ux = tf.matmul(inputs, U)
            U_cx, U_rx, U_gx = tf.split(Ux, 3, axis=1)

            W_r = vs.get_variable(
                "W_r", [self._hidden_size, self._hidden_size],
                dtype=tf.float32, initializer=U_init)
            W_g = vs.get_variable(
                "W_g", [self._hidden_size, self._hidden_size],
                dtype=tf.float32, initializer=U_init)
            W_rh = tf.matmul(state, W_r)
            W_gh = tf.matmul(state, W_g)

            bias_r = vs.get_variable(
                "bias_r", [self._hidden_size], dtype=tf.float32,
                initializer=b_init)
            bias_g = vs.get_variable(
                "bias_g", [self._hidden_size], dtype=tf.float32)
            bias_c = vs.get_variable(
                "bias_c", [self._hidden_size], dtype=tf.float32,
                initializer=mod_b_init)

            r_tmp = U_rx + W_rh + bias_r
            g_tmp = U_gx + W_gh + bias_g
            r = tf.sigmoid(r_tmp)
            g = tf.sigmoid(g_tmp)

            Unitaryh = _eunn_loop(
                state, self._capacity, self.diag_vec,
                self.off_vec, self.diag, self._fft)
            c = modrelu(tf.multiply(r, Unitaryh) + U_cx, bias_c)
            new_state = tf.multiply(g, state) + tf.multiply(1 - g, c)

        return new_state, new_state
