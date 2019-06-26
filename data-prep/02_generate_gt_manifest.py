import boto3
import json
import logging
import time
import argparse
import os

DEFAULT_BUCKET = "jbs-videos"

# LIMIT = 10000
DEFAULT_SAMPLING_RATE = 1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

s3 = boto3.resource('s3')

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-k", "--frames_s3_prefix", required=True, help="S3 prefix of the frames")
ap.add_argument("-b", "--frames_s3_bucket", required=False, help="S3 bucket of the frames", default=DEFAULT_BUCKET)
ap.add_argument("-r", "--sampling_rate", required=False, default=DEFAULT_SAMPLING_RATE,
                help="Sample one out of how many frames. e.g. 1 means use every frame. 30 means 1 out of every 30 frames will be used. Default to 1")
ap.add_argument("-d", "--working_directory", required=False, help="the directory to store files",
                default=".")


def generate_ground_truth_manifest(s3bucket, s3_prefix, sampling_rate, working_directory):
    my_bucket = s3.Bucket(s3bucket)
    count_frames_total = 0
    count_frames_included = 0

    manifest_filename = '{}_sampling_every_{}_ground_truth_manifest.json'.format(s3_prefix.split('/')[-2],
                                                                                 sampling_rate)
    manifest_filepath = os.path.join(working_directory, manifest_filename)
    logger.info("writing to manifest: {}".format(manifest_filepath))
    start = time.time()
    with open(manifest_filepath, 'w') as outfile:
        for i, s3_object in enumerate(my_bucket.objects.filter(Prefix=s3_prefix)):
            if s3_object.key.endswith('jpg'):
                count_frames_total += 1
                if count_frames_total % sampling_rate == 0:
                    obj = {}
                    obj['source-ref'] = 's3://' + s3_object.bucket_name + '/' + s3_object.key

                    # uncomment the line below if you are using the our example data
                    # obj = append_additional_metadata(obj, s3_object.key)

                    # Write manifest entry to file.
                    json.dump(obj, outfile)
                    outfile.write('\n')
                    count_frames_included += 1
                if count_frames_total % (sampling_rate * 100) == 0:
                    logger.info("processed {} frames. ".format(count_frames_total))
                    logger.info("took {:10.4f} seconds for 100".format(time.time() - start))
                    start = time.time()

        logger.info(
            "{} will be sent to ground truth out of {}".format(count_frames_included, count_frames_total))
    return manifest_filepath


def append_additional_metadata(obj, s3_key):
    # s3 object key will look something like blog_data/blue_box_0001.jpg
    # Get the filename from the object key
    filename = os.path.split(s3_key)[1]
    # get rid of the extension
    file_prefix = os.path.splitext(filename)[0]
    # split by underscore to get classes. Ex. filename) blue_box_0001
    classes = file_prefix.split('_')
    # Create manifest entry and write to file.
    obj['color'] = classes[0]
    obj['object'] = classes[1]
    return obj


def main():
    args = vars(ap.parse_args())
    s3_key = args["frames_s3_prefix"]
    if not s3_key.endswith("/"):
        s3_key += "/"
    s3_bucket = args["frames_s3_bucket"]
    sampling_rate = int(args["sampling_rate"])

    working_directory = args["working_directory"]
    if not os.path.isdir(working_directory):
        ap.error('--working_directory must be an existing directory')

    logger.info("storing files at: {}".format(working_directory))

    logger.info("arguments:")
    logger.info(args)

    manifest_filepath = generate_ground_truth_manifest(s3_bucket, s3_key, sampling_rate, working_directory)
    logger.info("Generated ground truth manifest: {}".format(manifest_filepath))


if __name__ == "__main__":
    main()
