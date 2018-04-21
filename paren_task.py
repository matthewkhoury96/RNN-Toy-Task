from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import argparse
import tensorflow as tf
import matplotlib.pyplot as plt

from EUNN import EUNNCell
from GORU import GORUCell
from Orthogonal_LSTM import Orthogonal_LSTM_Cell

from tensorflow.python.ops.rnn_cell_impl import RNNCell
from tensorflow.python.ops.rnn_cell_impl import BasicLSTMCell


def paren_data(T, n_data):
    MAX_COUNT = 10
    n_paren = 10
    n_noise = 10

    inputs = (np.random.rand(T, n_data) *
              (n_paren * 2 + n_noise)).astype(np.int32)
    counts = np.zeros((n_data, n_paren), dtype=np.int32)
    targets = np.zeros((T, n_data, n_paren), dtype=np.int32)
    opening_parens = (np.arange(0, n_paren) * 2)[None, :]
    closing_parens = opening_parens + 1
    for i in range(T):
        opened = np.equal(inputs[i, :, None], opening_parens)
        counts = np.minimum(MAX_COUNT, counts + opened)
        closed = np.equal(inputs[i, :, None], closing_parens)
        counts = np.maximum(0, counts - closed)
        targets[i, :, :] = counts

    x = np.transpose(inputs, [1, 0])
    y = np.transpose(targets, [1, 0, 2])

    return x, y


def plot_log_loss(iterations, losses, model):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.set_xlabel("Training Iterations")
    ax.set_ylabel("Loss (log-scale)")
    ax.set_title("Parenthesis Task")

    ax.plot(iterations, np.log(losses), color='b',
            label=model)
    ax.legend(loc=1)

    fig.savefig('plots/log_loss_{}.pdf'.format(model))


def main(model, T, n_iter, n_batch, n_hidden, capacity, complex, fft):

    # --- Set data params ----------------
    n_input = 30
    n_output = 10
    n_test = 10000

    n_steps = T
    n_classes = 21

    # --- Create graph and compute gradients ----------------------
    x = tf.placeholder("int32", [None, n_steps])
    y = tf.placeholder("int64", [None, n_steps, n_output])

    input_data = tf.one_hot(x, n_input, dtype=tf.float32)

    # --- Input to hidden layer ----------------------
    if model == "LSTM":
        cell = tf.nn.rnn_cell.BasicLSTMCell(
            n_hidden, state_is_tuple=True, forget_bias=1)
        hidden_out, _ = tf.nn.dynamic_rnn(cell, input_data, dtype=tf.float32)
    elif model == "GRU":
        cell = tf.nn.rnn_cell.GRUCell(n_hidden)
        hidden_out, _ = tf.nn.dynamic_rnn(cell, input_data, dtype=tf.float32)
    elif model == "EUNN":
        cell = EUNNCell(n_hidden, capacity, fft, complex)
        if complex:
            hidden_out_comp, _ = tf.nn.dynamic_rnn(
                cell, input_data, dtype=tf.complex64)
            hidden_out = tf.real(hidden_out_comp)
        else:
            hidden_out, _ = tf.nn.dynamic_rnn(
                cell, input_data, dtype=tf.float32)
    elif model == "GORU":
        cell = GORUCell(n_hidden, capacity, fft)
        hidden_out, _ = tf.nn.dynamic_rnn(cell, input_data, dtype=tf.float32)
    elif model == "Orthogonal_LSTM":
        cell = Orthogonal_LSTM_Cell(n_hidden, capacity, fft)
        hidden_out, _ = tf.nn.dynamic_rnn(cell, input_data, dtype=tf.float32)

    # --- Hidden Layer to Output ----------------------
    V_init_val = np.sqrt(6.) / np.sqrt(n_output + n_input)

    V_weights = tf.get_variable(
        "V_weights", shape=[n_hidden, n_classes * n_output],
        dtype=tf.float32,
        initializer=tf.random_uniform_initializer(-V_init_val, V_init_val))
    V_bias = tf.get_variable(
        "V_bias", shape=[n_classes * n_output],
        dtype=tf.float32, initializer=tf.constant_initializer(0.01))

    hidden_out_list = tf.unstack(hidden_out, axis=1)
    temp_out = tf.stack([tf.matmul(i, V_weights) for i in hidden_out_list])
    output_data = tf.reshape(tf.nn.bias_add(tf.transpose(
        temp_out, [1, 0, 2]), V_bias), [-1, n_steps, n_output, n_classes])

    # --- evaluate process ----------------------
    cost = tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(
        logits=output_data, labels=y))
    correct_pred = tf.equal(tf.argmax(output_data, 3), y)
    accuracy = tf.reduce_mean(tf.cast(correct_pred, tf.float32))

    # --- Initialization ----------------------
    optimizer = tf.train.AdamOptimizer(learning_rate=0.001).minimize(cost)
    init = tf.global_variables_initializer()

    # --- Training Loop ----------------------

    # Create some arrays to store training data
    iterations = []
    losses = []

    step = 0
    with tf.Session(config=tf.ConfigProto(log_device_placement=False,
                                          allow_soft_placement=False)) as sess:

        sess.run(init)

        while step < n_iter:
            batch_x, batch_y = paren_data(T, n_batch)

            sess.run(optimizer, feed_dict={x: batch_x, y: batch_y})

            acc, loss = sess.run([accuracy, cost], feed_dict={
                                 x: batch_x, y: batch_y})

            print("Iter " + str(step) + ", Minibatch Loss= " +
                  "{:.6f}".format(loss) + ", Training Accuracy= " +
                  "{:.5f}".format(acc))

            iterations.append(step)
            losses.append(loss)

            step += 1

        print("Optimization Finished!")

        # --- test ----------------------
        test_x, test_y = paren_data(T, n_test)

        test_acc = sess.run(accuracy, feed_dict={x: test_x, y: test_y})
        test_loss = sess.run(cost, feed_dict={x: test_x, y: test_y})
        print("Test result: Loss= " + "{:.6f}".format(test_loss) +
              ", Accuracy= " + "{:.5f}".format(test_acc))

        plot_log_loss(iterations, losses, model)


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Parenthesis Task")
    parser.add_argument("--model", default='GORU',
                        help='Model name: LSTM, GRU, EUNN, GORU')
    parser.add_argument('--T', '-T', type=int, default=100,
                        help='Parenthesis Task sequence length')
    parser.add_argument('--n_iter', '-I', type=int,
                        default=5000, help='training iteration number')
    parser.add_argument('--n_batch', '-B', type=int,
                        default=128, help='batch size')
    parser.add_argument('--n_hidden', '-H', type=int,
                        default=128, help='hidden layer size')
    parser.add_argument('--capacity', '-L', type=int, default=2,
                        help='Tunable style capacity, default value is 2')
    parser.add_argument('--complex', '-C', type=str, default="True",
                        help='Complex domain or Real domain for EUNN.' +
                        'Default is True: complex domain')
    parser.add_argument('--fft', '-F', type=str, default="True",
                        help='fft style, only for GORU, default is True')

    args = parser.parse_args()
    dict = vars(args)

    for i in dict:
        if (dict[i] == "False"):
            dict[i] = False
        elif dict[i] == "True":
            dict[i] = True

    kwargs = {
        'model': dict['model'],
        'T': dict['T'],
        'n_iter': dict['n_iter'],
        'n_batch': dict['n_batch'],
        'n_hidden': dict['n_hidden'],
        'capacity': dict['capacity'],
        'complex': dict['complex'],
        'fft': dict['fft'],
    }

    main(**kwargs)
