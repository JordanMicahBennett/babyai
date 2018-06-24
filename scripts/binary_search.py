#!/usr/bin/env python3

"""
Script to search the minimum number of demonstrations required to achieve a particular level of maximum performance bar (within a given range)
in a binary search manner.
python -m scripts.binary_search --env BabyAI-LevelName-v0 --demos-origin agent --val-episodes 100 --arch cnn1 --min-demo 10 --max-demo 1000 --batch-size <must be smaller than the min-demo>
"""

import numpy as np
import argparse
import csv
import os
from babyai.evaluate import evaluate
import babyai.utils as utils
from babyai.algos.imitation import ImitationLearning
import gym
import babyai
import torch

parser = argparse.ArgumentParser()
parser.add_argument("--env", required=True,
                    help="name of the environment to train on (REQUIRED)")
parser.add_argument("--demos-origin", required=True,
                    help="origin of the demonstrations: human | agent (REQUIRED)")
parser.add_argument("--lr", type=float, default=7e-4,
                    help="learning rate (default: 7e-4)")
parser.add_argument("--entropy-coef", type=float, default=0.2,
                    help="entropy term coefficient (default: 0.2)")
parser.add_argument("--recurrence", type=int, default=1,
                    help="number of timesteps gradient is backpropagated (default: 1)")
parser.add_argument("--optim-eps", type=float, default=1e-5,
                    help="Adam optimizer epsilon (default: 1e-5)")
parser.add_argument("--batch-size", type=int, default=50,
                    help="batch size (In case of memory, the batch size is the number of demos, otherwise, it is the number of frames)(default: 50)")
parser.add_argument("--no-instr", action="store_true", default=False,
                    help="don't use instructions in the model")
parser.add_argument("--instr-arch", default="gru",
                    help="arch to encode instructions, possible values: gru, conv, bow (default: gru)")
parser.add_argument("--no-mem", action="store_true", default=False,
                    help="don't use memory in the model")
parser.add_argument("--arch", default='cnn1',
                    help="image embedding architecture, possible values: cnn1, cnn2, filmcnn (default: cnn1)")
parser.add_argument("--discount", type=float, default=0.99,
                    help="discount factor (default: 0.99)")
parser.add_argument("--validation-interval", type=int, default=20,
                    help="number of epochs between two validation checks (default: 20)")
parser.add_argument("--val-episodes", type=int, default=1000,
                    help="number of episodes used for validation (default: 1000)")
parser.add_argument("--patience", type=int, default=3,
                    help="patience for early stopping (default: 3)")
parser.add_argument("--val-seed", type=int, default=0,
                    help="seed for environment used for validation (default: 0)")
parser.add_argument("--min-demo", type=int, default=50,
                    help="the minimum number of demonstrations to start searching (default: 50)")
parser.add_argument("--max-demo", type=int, default=3000,
                    help="the maximum number of demonstrations to start searching (default: 3000)")
parser.add_argument("--epsilon", type=int, default=0.02,
                    help="tolerable difference between mean rewards")
parser.add_argument("--test-seed", type=int, default=6,
                    help="seed used for testing a model (default: 6)")
parser.add_argument("--test-episodes", type=int, default=1000,
                    help="number of episodes used for testing (default: 1000)")
parser.add_argument("--argmax", action="store_true", default=False,
                    help="action with highest probability is selected for model agent while evaluating" )
parser.add_argument("--tb", action="store_true", default=False,
                    help="log into Tensorboard")

args = parser.parse_args()
seeds = [1, 2, 3, 4, 5]

result_dir = os.path.join(utils.storage_dir(), "binary_search_results")
if not(os.path.isdir(result_dir)):
    os.makedirs(result_dir)

file = open(os.path.join(result_dir, "{}_binary_search.csv").format(args.env),"a")
writer = csv.writer(file, delimiter=" ")

def run(num_demos):
    results = []
    for seed in seeds:
        args.model = "{}_{}_il_seed_{}_demos_{}".format(args.env, args.demos_origin, seed, num_demos)
        args.episodes = num_demos
        args.seed = seed
        il_learn = ImitationLearning(args)

        # Define logger and Tensorboard writer
        logger = utils.get_logger(il_learn.model_name)
        tb_writer = None
        if args.tb:
            from tensorboardX import SummaryWriter
            tb_writer = SummaryWriter(utils.get_log_dir(il_learn.model_name))

        # Log command, availability of CUDA, and model
        logger.info(args)
        logger.info("CUDA available: {}".format(torch.cuda.is_available()))
        logger.info(il_learn.acmodel)


        if not args.no_mem:
            il_learn.train(il_learn.train_demos, logger, tb_writer)
        else:
            il_learn.train(il_learn.flat_train_demos, logger, tb_writer)

        env = gym.make(args.env)
        utils.seed(args.test_seed)
        agent = utils.load_agent(args, env)
        env.seed(args.test_seed)

        logs = evaluate(agent, env, args.test_episodes)

        results.append(np.mean(logs["return_per_episode"]))
        writer.writerow([args.model, str(np.mean(logs["return_per_episode"]))])

    return np.mean(results)


min_demo = args.min_demo
max_demo = args.max_demo

return_min = run(min_demo)
return_max = run(max_demo)

max_performance_bar = return_max


while True:
    assert return_max >= return_min

    if (max_performance_bar-return_min) <= args.epsilon:
        print("Minimum No. of Samples Required = %d" % min_demo)
        break

    if np.log2(max_demo/min_demo) <= 0.5:
        print("Minimum No. of Samples Required = %d" % max_demo)
        print("Ratio : %.3f" % np.log2(max_demo/min_demo))
        break

    mid_demo = (min_demo+max_demo)//2

    return_mid = run(mid_demo)

    assert return_mid >= return_min and return_mid <= return_max

    if (max_performance_bar-return_mid) >= args.epsilon:
        min_demo = mid_demo
        return_min = return_mid
    else:
        max_demo = mid_demo
        return_max = return_mid

    max_performance_bar = max(max_performance_bar, return_max)