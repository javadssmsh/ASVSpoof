from __future__ import print_function

import argparse, os

import chainer
from chainer import cuda
from chainer.dataset import concat_examples
from chainer.datasets import tuple_dataset
import chainer.links as L
import chainer.functions as F
from chainer import serializers
from chainer import training
from chainer.training import extensions
import numpy as np
from data_loader import DataSet, load_data, DataSetOnLine
from model import *
from lcnn import LightCNN_29Layers

def convert_batch(batch, device=None):
    batch = np.array(batch)
    x = np.vstack(batch[:,0])
    y = np.hstack(batch[:,1])

    if device is None:
        return (x, y)
    if device >= 0:
        x = cuda.to_gpu(x, device)
        y = cuda.to_gpu(y, device)
        return (x, y)

def cnn_iter(batchsize):
    train = DataSetOnLine(mode='train', feat_type='fft', buf=False)
    dev = DataSetOnLine(mode='dev', feat_type='fft', buf=False)

    train_iter = chainer.iterators.MultiprocessIterator(train, batchsize, n_prefetch=2, shared_mem=100*1024*1024)
    dev_iter = chainer.iterators.MultiprocessIterator(dev, batchsize, n_prefetch=2, shared_mem=100*1024*1024, repeat=False, shuffle=False)

    return train_iter, dev_iter

def dnn_iter(batchsize):
    # extract all feature
    train_data, train_label, _ = load_data()
    train_data = np.vstack(train_data)
    mean = np.mean(train_data, axis=0)
    std = np.std(train_data, axis=0)
    train_data = (train_data - mean) / std
    dev_data, dev_label, _ = load_data(mode='dev')
    dev_data = np.vstack(dev_data)
    mean = np.mean(dev_data, axis=0)
    std = np.std(dev_data, axis=0)
    dev_data = (dev_data - mean) / std

    train = DataSet(train_data, np.hstack(train_label))
    print(len(train))

    dev = DataSet(np.vstack(dev_data), np.hstack(dev_label))
    print(len(dev))

    train_iter = chainer.iterators.SerialIterator(train, batchsize)
    dev_iter = chainer.iterators.SerialIterator(dev, batchsize, repeat=False, shuffle=False)

    return train_iter, dev_iter

def main():
    parser = argparse.ArgumentParser(description='Chainer example: MNIST')
    parser.add_argument('--batchsize', '-b', type=int, default=20, help='Number of images in each mini-batch')
    parser.add_argument('--epoch', '-e', type=int, default=100, help='Number of sweeps over the dataset to train')
    parser.add_argument('--lr', '-l', type=float, default=1e-5, help='learning rate')
    parser.add_argument('--gpu', '-g', type=int, default=0, help='GPU ID (negative value indicates CPU)')
    parser.add_argument('--out', '-o', default='dnn', help='Directory to output the result')
    parser.add_argument('--resume', '-r', default='', help='Resume the training from snapshot')
    parser.add_argument('--unit', '-u', type=int, default=1024, help='Number of units')
    parser.add_argument('--noplot', dest='plot', action='store_false', help='Disable PlotReport extension')

    parser.add_argument('--net', '-n', default='dnn', help='Nnet type for choosing iterators')
    args = parser.parse_args()

    try:
        os.mkdir(args.out)
    except:
        print('')

    print('GPU: {}'.format(args.gpu))
    print('# unit: {}'.format(args.unit))
    print('# Minibatch-size: {}'.format(args.batchsize))
    print('# epoch: {}'.format(args.epoch))
    print('')

    # Set up a neural network to train
    model = L.Classifier(DNN())
    if args.gpu >= 0:
        # Make a speciied GPU current
        chainer.cuda.get_device_from_id(args.gpu).use()
        model.to_gpu()  # Copy the model to the GPU

    # Setup an optimizer
    optimizer = chainer.optimizers.MomentumSGD(lr=args.lr)
    optimizer.setup(model)
    optimizer.add_hook(chainer.optimizer.WeightDecay(5e-4))

    if args.net == 'cnn':
        train_iter, dev_iter = cnn_iter(args.batchsize)
    else:
        train_iter, dev_iter = dnn_iter(args.batchsize)

    # Set up a trainer
    updater = training.StandardUpdater(train_iter, optimizer, converter=convert_batch, device=args.gpu)
    trainer = training.Trainer(updater, (args.epoch, 'epoch'), out=args.out)

    # Evaluate the model with the test dataset for each epoch
    trainer.extend(extensions.Evaluator(dev_iter, model, device=args.gpu))

    # Reduce the learning rate by half every 25 epochs.
    trainer.extend(extensions.ExponentialShift('lr', 0.5), trigger=(10, 'epoch'))

    # Dump a computational graph from 'loss' variable at the first iteration
    # The "main" refers to the target link of the "main" optimizer.
    trainer.extend(extensions.dump_graph('main/loss'))

    # Take a snapshot at each epoch
    trainer.extend(extensions.snapshot(), trigger=(args.epoch, 'epoch'))

    # Write a log of evaluation statistics for each epoch
    trainer.extend(extensions.LogReport())

    # Print selected entries of the log to stdout
    # Here "main" refers to the target link of the "main" optimizer again, and
    # "validation" refers to the default name of the Evaluator extension.
    # Entries other than 'epoch' are reported by the Classifier link, called by
    # either the updater or the evaluator.
    trainer.extend(extensions.PrintReport(
        ['epoch', 'main/loss', 'validation/main/loss',
         'main/accuracy', 'validation/main/accuracy', 'elapsed_time']))

    # Print a progress bar to stdout
    trainer.extend(extensions.ProgressBar())

    if args.resume:
        # Resume from a snapshot
        chainer.serializers.load_npz(args.resume, trainer)

    # Run the training
    trainer.run()

if __name__ == '__main__':
    main()