import os
import imageio
import boto3
from urllib.parse import urlparse
import logging
import cv2
import argparse
import common_utils as utils
from augmentation_options import Transform

s3 = boto3.resource('s3')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-m", "--manifest_uri", required=True, help="S3 path to the manifest")
ap.add_argument("-b", "--output_s3_bucket", required=True, help="S3 bucket to upload result images")
ap.add_argument("-d", "--working_directory", required=False, help="the root directory to store video and frames",
                default=".")




def flip(image_local_path, working_dir, x_axis=True):
    img = imageio.imread(image_local_path)
    flipped_image = cv2.flip(img, 1 if x_axis else 0)
    fname = os.path.split(image_local_path)[1]

    # If original file is "test-1.jpg", a x-flipped file will be named "test-1-x-flip.jpg"
    flipped_fname_suffix = '-x-flip.' if x_axis else '-y-flip.'
    flipped_fname = fname.replace('.', flipped_fname_suffix)

    flipped_fpath = os.path.join(working_dir, flipped_fname)
    imageio.imwrite(flipped_fpath, flipped_image)
    logger.info("wrote image to {}".format(flipped_fpath))
    return flipped_fpath


def rotate(image_local_path, working_dir, cw=True):
    img = imageio.imread(image_local_path)
    rotated = cv2.transpose(img)
    rotated = cv2.flip(rotated, 1 if cw else 0)
    fname = os.path.split(image_local_path)[1]

    # If original file is "test-1.jpg", a cw rotated file will be named "test-1-cw-rotate.jpg"
    rotated_fname_suffix = "-cw-rotate." if cw else '-ccw-rotate.'
    rotated_fname = fname.replace('.', rotated_fname_suffix)

    rotated_fpath = os.path.join(working_dir, rotated_fname)
    imageio.imwrite(rotated_fpath, rotated)
    logger.info("wrote image to {}".format(rotated_fpath))
    return rotated_fpath


def transform_and_upload(transformation, image_path, working_directory, s3_bucket, s3_prefix, cleanup):
    
    if transformation is Transform.X_FLIP:
        transformed = flip(image_path, working_directory, x_axis=True)
    elif transformation is Transform.Y_FLIP:
        transformed = flip(image_path, working_directory, x_axis=False)
    elif transformation is Transform.CW_ROTATE:
        transformed = rotate(image_path, working_directory, cw=True)
    else:
        transformed = rotate(image_path, working_directory, cw=False)
    utils.upload_file(transformed, s3_bucket, s3_prefix)
    if cleanup:
        os.remove(transformed)


def transform_img(img_s3_uri, working_directory, output_s3_bucket, cleanup=True):
    o = urlparse(img_s3_uri)
    s3_bucket = o.netloc
    s3_key = o.path.lstrip('/')

    img_fname = os.path.split(s3_key)[1]
    img_id = os.path.splitext(img_fname)[0]
    logger.info("image: {}".format(img_id))

    img_ccw = 'frames/ccw/' + img_id + '-ccw-rotate.jpg'
    
    if utils.exists_in_s3(output_s3_bucket, img_ccw):
        logger.info("augmentation already exists: s3://{}/{}".format(output_s3_bucket, img_ccw))
    else:
        logger.info("augmentation does not exist: s3://{}/{}".format(output_s3_bucket, img_ccw))
        image_path = utils.download_file(img_s3_uri, working_directory)
        transform_and_upload(transformation=Transform.X_FLIP, image_path=image_path,
                             working_directory=working_directory, s3_bucket=output_s3_bucket, s3_prefix='frames/x-flipped',
                             cleanup=cleanup)
        transform_and_upload(transformation=Transform.Y_FLIP, image_path=image_path,
                             working_directory=working_directory, s3_bucket=output_s3_bucket, s3_prefix='frames/y-flipped',
                             cleanup=cleanup)
        transform_and_upload(transformation=Transform.CW_ROTATE, image_path=image_path,
                             working_directory=working_directory, s3_bucket=output_s3_bucket, s3_prefix='frames/cw',
                             cleanup=cleanup)
        transform_and_upload(transformation=Transform.CCW_ROTATE, image_path=image_path,
                             working_directory=working_directory, s3_bucket=output_s3_bucket, s3_prefix='frames/ccw',
                             cleanup=cleanup)
        if cleanup:
            os.remove(image_path)


def main():
    args = vars(ap.parse_args())
    manifest_s3_uri = args["manifest_uri"]

    output_s3_bucket = args['output_s3_bucket']
    
    working_directory = args["working_directory"]
    if not os.path.isdir(working_directory):
        utils.create_tmp_dir(working_directory)
    logger.info("working directory: {}".format(working_directory))

    manifest_file = utils.download_file(manifest_s3_uri, working_dir=working_directory)
    manifest_lines = utils.read_manifest_file(manifest_file)
    print(len(manifest_lines))
    for line in manifest_lines:
        img_s3_uri = line['source-ref']
        transform_img(img_s3_uri, working_directory, output_s3_bucket)


if __name__ == "__main__":
    main()
