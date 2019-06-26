import json
import os
import skimage
import skimage.io as io
import skimage.transform
import numpy as np
import torchvision
import torch
import boto3
import shutil
import argparse
import logging
import time
from urllib.parse import urlparse  # python 3

# from urlparse import urlparse  # python 2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# construct the argument parser and parse the arguments

ap = argparse.ArgumentParser()
ap.add_argument("-k", "--manifest_s3_key", required=True, help="S3 key of the manifest")
ap.add_argument("-b", "--manifest_s3_bucket", required=True, help="S3 bucket of the manifest")
ap.add_argument("-d", "--working_directory", required=False, help="the root directory to store video and frames",
                default=".")
ap.add_argument("-i", "--image_directory", required=False,
                help="If the frames are on local disk, location to the image (this will avoid downloading the images agin)")

ap.add_argument("-p", "--preview_prefix", required=False, default="previews/gt-labeling-manifest/",
                help="the S3 prefix to upload the video preview/visualization. default is previews/gt-labeling-manifest/")

s3 = boto3.resource('s3')

IMG_DIM = 128
VISUALIZE_EVERY_X_FRAMES = 1


def get_image_list_from_manifest(manifest_s3_bucket, manifest_s3_key):
    manifest_name = manifest_s3_key.split('/')[-1]
    s3.Bucket(manifest_s3_bucket).download_file(manifest_s3_key, manifest_name)
    with open(manifest_name, 'r') as f:
        images = [json.loads(line)['source-ref'] for line in f.readlines()]
        return images


def sample_frames(tmp_folder, images, image_directory):
    sampled_frames = np.empty((0, 3, IMG_DIM, IMG_DIM), dtype=np.float32)  # B, C, H, W
    i = 0

    for s3_path in images:
        if i % VISUALIZE_EVERY_X_FRAMES == 0:
            o = urlparse(s3_path)
            image_name = s3_path.split('/')[-1]

            if image_directory is not None and os.path.exists(os.path.join(image_directory, image_name)):
                image_path = os.path.join(image_directory, image_name)
                logger.debug("{} already exists".format(image_name))
            else:
                image_path = tmp_folder + '/' + image_name
                s3_key = o.path.lstrip('/')
                s3.Bucket(o.netloc).download_file(s3_key, image_path)
            img = skimage.img_as_float(skimage.io.imread(image_path)).astype(np.float32)
            img = skimage.transform.resize(img, (IMG_DIM, IMG_DIM))  # H, W, C
            img = img.swapaxes(1, 2).swapaxes(0, 1)  # C, H, W
            sampled_frames = np.append(sampled_frames, np.array([img]), axis=0)
        i += 1
    logger.info("sampled {} frames".format(i))
    return sampled_frames


def generate_preview_image(sampled_frames, preview_name):
    grid = (torchvision.utils.make_grid(torch.from_numpy(sampled_frames)))
    torchvision.utils.save_image(grid, preview_name)


def create_tmp_dir(tmp_folder):
    if not os.path.exists(tmp_folder):
        os.makedirs(tmp_folder)
    else:
        shutil.rmtree(tmp_folder)
        os.makedirs(tmp_folder)


def main():
    start = time.time()
    args = vars(ap.parse_args())
    manifest_s3_key = args["manifest_s3_key"]
    manifest_s3_bucket = args["manifest_s3_bucket"]
    logger.info("manifest: s3://{}/{}".format(manifest_s3_bucket, manifest_s3_key))

    working_directory = args["working_directory"]
    if not os.path.isdir(working_directory):
        ap.error('--working_directory must be an existing directory')

    image_directory = args["image_directory"]

    manifest_name = manifest_s3_key.split('/')[-1].split('.')[0]
    tmp_folder = os.path.join(working_directory, manifest_name)
    create_tmp_dir(tmp_folder)

    images = get_image_list_from_manifest(manifest_s3_bucket, manifest_s3_key)

    frames = sample_frames(tmp_folder, images, image_directory)
    preview_name = manifest_s3_key.split('/')[-1].split('.')[0] + "_preview.png"
    preview_name = os.path.join(working_directory, preview_name)
    logger.info("saving preview to {} ".format(preview_name))

    generate_preview_image(frames, preview_name)

    preview_prefix = args["preview_prefix"]
    if not preview_prefix.endswith("/"):
        preview_prefix += "/"

    s3.Bucket(manifest_s3_bucket).upload_file(preview_name, preview_prefix + preview_name)
    logger.info("uploaded preview image to {}".format(preview_prefix + preview_name))
    # os.remove(preview_name)
    shutil.rmtree(tmp_folder)
    logger.info("processed {} for {:10.4f} seconds.".format(manifest_s3_key, time.time() - start))


if __name__ == "__main__":
    main()
