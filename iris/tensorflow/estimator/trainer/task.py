# Copyright 2018 Google Inc. All Rights Reserved. Licensed under the Apache
# License, Version 2.0 (the "License"); you may not use this file except in
# compliance with the License. You may obtain a copy of the License at
# http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations under
# the License.
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import argparse
import logging
import json
import os
import sys

from . import model

import tensorflow as tf
from tensorflow.contrib.training.python.training import hparam


def get_args():
  """Argument parser.

	 Returns:
		Dictionary of arguments.
	"""
  parser = argparse.ArgumentParser()
  # Input Arguments.
  parser.add_argument(
      '--train-files',
      help='GCS or local paths to training data',
      nargs='+',
      required=True)
  parser.add_argument(
      '--eval-files',
      help='GCS or local paths to evaluation data',
      nargs='+',
      required=True)
  parser.add_argument(
      '--job-dir',
      help='GCS location to write checkpoints and export models',
      required=True)
  # Train arguments.
  parser.add_argument(
      '--train-steps',
      help="""
        Steps to run the training job for. If --num-epochs is not specified,
        this must be. Otherwise the training job will run indefinitely.""",
      type=int,
      default=400)
  parser.add_argument(
      '--eval-steps',
      help='Number of steps to run evalution for at each checkpoint',
      type=int,
      default=100)
  parser.add_argument(
      '--num-epochs',
      help="""
        Maximum number of training data epochs on which to train.
        If both --train-steps and --num-epochs are specified,
        the training job will run for --train-steps or --num-epochs,
        whichever occurs first. If unspecified will run for --train-steps.""",
      type=int,
      default=200)
  parser.add_argument(
      '--learning-rate',
      help='Learning rate',
      type=float,
      default=0.01)
  parser.add_argument(
      '--train-batch-size',
      help='Batch size for training steps',
      type=int,
      default=32)
  parser.add_argument(
      '--eval-batch-size',
      help='Batch size for evaluation steps',
      type=int,
      default=32)
  return parser.parse_args()


def _setup_logging():
  """Sets up logging."""
  logger = logging.getLogger()
  logger.setLevel(logging.INFO)
  # Set tf logging to avoid duplicate logging. If the handlers are not removed,
  # then we will have duplicate logging :
  # From tf loggging written to stderr stream, and
  # From python logger written to stdout stream.
  tf_logger = logging.getLogger('tensorflow')
  while tf_logger.handlers:
    tf_logger.removeHandler(tf_logger.handlers[0])
   # Redirect INFO logs to stdout
  stdout_handler = logging.StreamHandler(sys.stdout)
  stdout_handler.setLevel(logging.INFO)
  logger.addHandler(stdout_handler)
   # Suppress C++ level warnings.
  os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'


def _get_session_config_from_env_var():
  """Returns a tf.ConfigProto instance with appropriate device_filters set."""

  tf_config = json.loads(os.environ.get('TF_CONFIG', '{}'))
  if (tf_config and 'task' in tf_config and 'type' in tf_config['task'] and
      'index' in tf_config['task']):
    # Master should only communicate with itself and ps.
    if tf_config['task']['type'] == 'master':
      return tf.ConfigProto(device_filters=['/job:ps', '/job:master'])
    # Worker should only communicate with itself and ps.
    elif tf_config['task']['type'] == 'worker':
      return tf.ConfigProto(device_filters=[
          '/job:ps',
          '/job:worker/task:%d' % tf_config['task']['index']
      ])
  return None


def train_and_evaluate(hparams):
  """Runs the training and evaluate using the high level API."""

  # Running configuration.
  run_config = tf.estimator.RunConfig(
      session_config=_get_session_config_from_env_var(),
      save_checkpoints_steps=100,
      save_summary_steps=100,
      model_dir=hparams.job_dir)

  # Create TrainSpec.
  train_input_fn = lambda: model.input_fn(
      filename=hparams.train_files,
      batch_size=hparams.train_batch_size,
      shuffle=True)
  train_spec = tf.estimator.TrainSpec(
      train_input_fn, max_steps=hparams.train_steps)

  # Define evaluating spec. Don't shuffle evaluation data.
  exporter = tf.estimator.FinalExporter('exporter',
                                        model.serving_input_receiver_fn)
  # Create EvalSpec.
  eval_input_fn = lambda: model.input_fn(
      filename=hparams.eval_files,
      batch_size=hparams.eval_batch_size,
      shuffle=False)
  eval_spec = tf.estimator.EvalSpec(
      eval_input_fn,
      steps=hparams.eval_steps,
      exporters=[exporter],
      name='iris-eval')

  print('Model dir: %s' % run_config.model_dir)

  # Create the Estimator.
  estimator = model.build_estimator(
      # Construct layers sizes.
      config=run_config,
      learning_rate=hparams.learning_rate,
      hidden_units=[10, 20, 10],
      num_classes=3)

  # Train and evaluate the model.
  tf.estimator.train_and_evaluate(estimator, train_spec, eval_spec)


if __name__ == '__main__':
  args = get_args()
  _setup_logging()

  hparams = hparam.HParams(**args.__dict__)
  train_and_evaluate(hparams)