#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
sys.path.insert(0, 'scripts/utils/evaluation/build')

if 'linux' in sys.platform:
    import matplotlib
    matplotlib.use('Agg')

import argparse
import evaluation
import os
import re
import glob
import cv2 as cv
import numpy as np
import matplotlib.pyplot as plt

PATCH_SIZE = 16
PATCH_PIXELS = PATCH_SIZE ** 2
STRIDE = 16
NUM_RATIO = 0.1


def get_relaxed_pre_rec(p_patch, l_patch):
    positive = np.sum(p_patch)
    prec_tp = evaluation.relax_precision(p_patch, l_patch, 3)
    true = np.sum(l_patch)
    recall_tp = evaluation.relax_recall(p_patch, l_patch, 3)

    return positive, prec_tp, true, recall_tp


def get_pre_rec(positive, prec_tp, true, recall_tp, steps):
    pre_rec = []
    breakeven = []
    for t in range(steps):
        # if positive[t] < prec_tp[t] or true[t] < recall_tp[t]:
        #     sys.exit('calculation is wrong')
        pre = float(prec_tp[t]) / positive[t] if positive[t] > 0 else 0
        rec = float(recall_tp[t]) / true[t] if true[t] > 0 else 0
        pre_rec.append([pre, rec])
        if pre != 1 and rec != 1 and pre > 0 and rec > 0:
            breakeven.append([pre, rec])
    pre_rec = np.asarray(pre_rec)
    breakeven = np.asarray(breakeven)
    breakeven_pt = np.abs(breakeven[:, 0] - breakeven[:, 1]).argmin()
    breakeven_pt = breakeven[breakeven_pt]

    return pre_rec, breakeven_pt


def get_complex_regions(args, label_fn, pred_fns):
    fn = re.search('(.+)\.tif', os.path.basename(label_fn)).groups()[0]
    pred = np.load(pred_fns[fn])
    label = cv.imread(label_fn, cv.IMREAD_GRAYSCALE)
    label = label[args.pad + args.offset - 1:
                  args.pad + args.offset - 1 + pred.shape[0],
                  args.pad + args.offset - 1:
                  args.pad + args.offset - 1 + pred.shape[1]]

    thresh_evals = []
    for thresh in range(args.steps):
        pred_th = np.zeros(pred.shape, dtype=np.int32)
        th = thresh / float(args.steps - 1)
        for ch in range(pred.shape[2]):
            pred_th[:, :, ch] = np.array(pred[:, :, ch] >= th, dtype=np.int32)

        patch_evals = []
        for y in range(0, label.shape[0], STRIDE):
            for x in range(0, label.shape[1], STRIDE):
                if (y + PATCH_SIZE) >= label.shape[0]:
                    y = label.shape[0] - PATCH_SIZE
                if (x + PATCH_SIZE) >= label.shape[1]:
                    x = label.shape[1] - PATCH_SIZE

                l_patch = label[y:y + PATCH_SIZE, x:x + PATCH_SIZE]
                bgnd_ch = np.array(l_patch == 0, dtype=np.int32)
                bldg_ch = np.array(l_patch == 1, dtype=np.int32)
                road_ch = np.array(l_patch == 2, dtype=np.int32)
                l_patch = [bgnd_ch, bldg_ch, road_ch]

                num_bldg_pix = np.sum(bldg_ch)
                num_road_pix = np.sum(road_ch)

                # if ((num_bldg_pix > (PATCH_PIXELS * NUM_RATIO)) and
                #         (num_road_pix > (PATCH_PIXELS * NUM_RATIO))):
                if ((num_bldg_pix > 0) and (num_road_pix > 0)):
                    region_eval = []
                    for ch in range(pred.shape[2]):
                        p = pred_th[y:y + PATCH_SIZE, x:x + PATCH_SIZE, ch]
                        rpr = get_relaxed_pre_rec(p, l_patch[ch])
                        region_eval.append(list(rpr))
                    patch_evals.append(region_eval)
        evals = np.zeros((pred.shape[2], 4))
        for r in patch_evals:
            evals += np.array(r)
        thresh_evals.append(evals)
    thresh_evals = np.array(thresh_evals)

    return thresh_evals


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--result_dir', type=str)
    parser.add_argument('--test_map_dir', type=str)
    parser.add_argument('--pad', type=int, default=24)
    parser.add_argument('--offset', type=int, default=8)
    parser.add_argument('--steps', type=int, default=256)
    args = parser.parse_args()

    pred_fns = []
    for result in glob.glob('{}/*.npy'.format(args.result_dir)):
        fn = re.search('(.+)\.npy', os.path.basename(result)).groups()[0]
        pred_fns.append((fn, result))
    pred_fns = dict(pred_fns)

    args.out_dir = '{}/ratio-{:.2f}'.format(args.result_dir, NUM_RATIO)
    if not os.path.exists(args.out_dir):
        os.makedirs(args.out_dir)

    # threshold, channels, (positive, prec_tp, true, recall_tp)
    n_ch = np.load(list(pred_fns.items())[0][1]).shape[2]
    evals = np.zeros((256, n_ch, 4))
    for label_fn in glob.glob('{}/*.tif*'.format(args.test_map_dir)):
        print(label_fn)
        evals += get_complex_regions(args, label_fn, pred_fns)

    for ch in range(n_ch):
        e = evals[:, ch, :]
        pre_rec, breakeven_pt = \
            get_pre_rec(e[:, 0], e[:, 1], e[:, 2], e[:, 3], args.steps)

        plt.clf()
        plt.plot(pre_rec[:, 0], pre_rec[:, 1])
        plt.plot(breakeven_pt[0], breakeven_pt[1],
                 'x', label='breakeven recall: %f' % (breakeven_pt[1]))
        plt.ylabel('recall')
        plt.xlabel('precision')
        # plt.ylim([0.0, 1.1])
        # plt.xlim([0.0, 1.1])
        plt.legend(loc='lower left')
        plt.grid(linestyle='--')
        plt.savefig('{}/pre_rec_{}.png'.format(args.out_dir, ch))
