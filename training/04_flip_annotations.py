import os
from urllib.parse import urlparse
import logging
import argparse
from augmentation_options import Transform

import common_utils as utils

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-m", "--manifest_uri", required=True, help="S3 path to the manifest")
ap.add_argument("-p", "--new_manifest_prefix", required=True, help="s3 prefix of the new manifests")
ap.add_argument("-d", "--working_directory", required=False, help="the root directory to store video and frames",
                default=".")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def transform_annotations(manifest_line, transformation, s3_bucket):
    box_annotations = manifest_line['bb']['annotations']
    image_size = manifest_line['bb']['image_size'][0]
    s3_uri = manifest_line["source-ref"]
    fname = s3_uri.split("/")[-1]

    new_manifest_line = manifest_line.copy()

    if transformation is Transform.X_FLIP:
        transformed_fname = fname.split(".")[0] + "-x-flip." + fname.split(".")[1]
        prefix = "frames/x-flipped"
        bbs, new_image_size = x_flip_bb(box_annotations, image_size)
    elif transformation is Transform.Y_FLIP:
        transformed_fname = fname.split(".")[0] + "-y-flip." + fname.split(".")[1]
        prefix = "frames/y-flipped"
        bbs, new_image_size = y_flip_bb(box_annotations, image_size)
    elif transformation is Transform.CCW_ROTATE:
        transformed_fname = fname.split(".")[0] + "-ccw-rotate." + fname.split(".")[1]
        prefix = "frames/ccw"
        bbs, new_image_size = ccw_bb(box_annotations, image_size)
    elif transformation is Transform.CW_ROTATE:
        transformed_fname = fname.split(".")[0] + "-cw-rotate." + fname.split(".")[1]
        prefix = "frames/cw"
        bbs, new_image_size = cw_bb(box_annotations, image_size)

    new_manifest_line["source-ref"] = "s3://{}/{}/{}".format(s3_bucket, prefix, transformed_fname)
    new_manifest_line['bb'] = {
        'annotations': bbs,
        'image_size': [new_image_size]
    }
    return new_manifest_line


def y_flip_bb(box_annotations, image_size):
    image_height = image_size['height']

    vertically_flipped_bb = []
    for bb in box_annotations:
        y_flip_bb = {'class_id': bb['class_id'],
                     'width': bb['width'],
                     'left': bb['left'],
                     'height': bb['height'],
                     'top': image_height - (bb['top'] + bb['height'])}
        vertically_flipped_bb.append(y_flip_bb)
    return vertically_flipped_bb, image_size.copy()


def x_flip_bb(box_annotations, image_size):
    image_width = image_size['width']
    horizontal_flipped_bb = []
    for bb in box_annotations:
        x_flip_bb = {'class_id': bb['class_id'],
                     'top': bb['top'],
                     'width': bb['width'],
                     'height': bb['height'],
                     'left': image_width - (bb['left'] + bb['width'])}
        horizontal_flipped_bb.append(x_flip_bb)
    return horizontal_flipped_bb, image_size.copy()


def ccw_bb(box_annotations, image_size):
    image_width = image_size['width']
    image_height = image_size['height']

    ccw_rotated = []
    for bb in box_annotations:
        new_bb = {'class_id': bb['class_id'],
                  'left': bb['top'],
                  'width': bb['height'],
                  'height': bb['width'],
                  'top': image_width - (bb['left'] + bb['width'])
                  }
        ccw_rotated.append(new_bb)

    new_image_size = image_size.copy()
    new_image_size['width'] = image_height
    new_image_size['height'] = image_width
    return ccw_rotated, new_image_size


def cw_bb(box_annotations, image_size):
    image_width = image_size['width']
    image_height = image_size['height']

    cw_rotated = []
    for bb in box_annotations:
        new_bb = {'class_id': bb['class_id'],
                  'width': bb['height'],
                  'height': bb['width'],
                  'top': bb['left'],
                  'left': image_height - (bb['top'] + bb['height'])
                  }
        cw_rotated.append(new_bb)

    new_image_size = image_size.copy()
    new_image_size['width'] = image_height
    new_image_size['height'] = image_width
    return cw_rotated, new_image_size


def main():
    args = vars(ap.parse_args())
    manifest_s3_uri = args["manifest_uri"]

    o = urlparse(manifest_s3_uri)
    s3_bucket = o.netloc

    s3_prefix = args["new_manifest_prefix"]

    working_directory = args["working_directory"]
    if not os.path.isdir(working_directory):
        utils.create_tmp_dir(working_directory)
    logger.info("working directory: {}".format(working_directory))

    manifest_file = utils.download_file(manifest_s3_uri, working_dir=working_directory)
    manifest_lines = utils.read_manifest_file(manifest_file)
    print(len(manifest_lines))

    x_flip_manifest = []
    y_flip_manifest = []
    ccw_rotate_manifest = []
    cw_rotate_manifest = []
    for line in manifest_lines:
        x_flip_manifest.append(transform_annotations(line, Transform.X_FLIP, s3_bucket))
        y_flip_manifest.append(transform_annotations(line, Transform.Y_FLIP, s3_bucket))
        ccw_rotate_manifest.append(transform_annotations(line, Transform.CCW_ROTATE, s3_bucket))
        cw_rotate_manifest.append(transform_annotations(line, Transform.CW_ROTATE, s3_bucket))

    x_flip_manifest_name = os.path.join(working_directory, 'x-flipped.json')
    n = utils.write_manifest_file(x_flip_manifest, x_flip_manifest_name)
    logger.info("wrote {} lines to {}".format(n, x_flip_manifest_name))
    utils.upload_file(x_flip_manifest_name, s3_bucket, s3_prefix)
    logger.info("uploaded {} to s3://{}/{}".format(x_flip_manifest_name, s3_bucket, s3_prefix))

    y_flip_manifest_name = os.path.join(working_directory, 'y-flipped.json')
    n = utils.write_manifest_file(y_flip_manifest, y_flip_manifest_name)
    logger.info("wrote {} lines to {}".format(n, y_flip_manifest_name))
    utils.upload_file(y_flip_manifest_name, s3_bucket, s3_prefix)
    logger.info("uploaded {} to s3://{}/{}".format(y_flip_manifest_name, s3_bucket, s3_prefix))

    ccw_rotate_manifest_name = os.path.join(working_directory, 'ccw_rotated.json')
    n = utils.write_manifest_file(ccw_rotate_manifest, ccw_rotate_manifest_name)
    logger.info("wrote {} lines to {}".format(n, ccw_rotate_manifest_name))
    utils.upload_file(ccw_rotate_manifest_name, s3_bucket, s3_prefix)
    logger.info("uploaded {} to s3://{}/{}".format(ccw_rotate_manifest_name, s3_bucket, s3_prefix))

    cw_rotate_manifest_name = os.path.join(working_directory, 'cw_rotated.json')
    n = utils.write_manifest_file(cw_rotate_manifest, cw_rotate_manifest_name)
    logger.info("wrote {} lines to {}".format(n, cw_rotate_manifest_name))
    utils.upload_file(cw_rotate_manifest_name, s3_bucket, s3_prefix)
    logger.info("uploaded {} to s3://{}/{}".format(cw_rotate_manifest_name, s3_bucket, s3_prefix))
    
    all_manifest = manifest_lines + x_flip_manifest + y_flip_manifest + ccw_rotate_manifest + cw_rotate_manifest 
    all_manifest_name = os.path.join(working_directory, 'all_augmented.json')
    n = utils.write_manifest_file(all_manifest, all_manifest_name)   
    logger.info("wrote {} lines to {}".format(n, all_manifest_name))
    utils.upload_file(all_manifest_name, s3_bucket, s3_prefix)
    logger.info("uploaded {} to s3://{}/{}".format(all_manifest_name, s3_bucket, s3_prefix))



if __name__ == "__main__":
    main()
