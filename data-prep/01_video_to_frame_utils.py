from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

import os
import cv2
import logging
import skimage
import skimage.io as io
import skimage.transform
import numpy as np
import torchvision
import torch
import time
import boto3
import shutil
import argparse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
session = boto3.Session()
s3 = session.resource('s3')

IMG_DIM = 128  # the width and height to resize the frames for preview
REPORT_STATUS = 500 # number of frames to report progress

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-k", "--video_s3_key", required=True, help="S3 key of the video")
ap.add_argument("-b", "--video_s3_bucket", required=True, help="S3 bucket of the video")
ap.add_argument("-d", "--working_directory", required=False, help="the root directory to store video and frames",
                default=".")
ap.add_argument("-v", "--visualize_video", type=bool, required=False, default=True,
                help="Whether to generate a preview for the frames in the video.")
ap.add_argument("-o", "--output_s3_bucket", required=True, help="S3 bucket to store outputs")

ap.add_argument("-r", "--visualize_sample_rate", type=int, required=False, default=1,
                help="For visualizing the video, how frequent (in seconds) to sample the frames. default to sample every second.")
ap.add_argument("-u", "--upload_frames", action='store_true',
                help="Whether to have the script upload the frames. If you choose not to, the frames will be stored" +
                     " on local disk and you can use e.g. s3 sync command line tool to upload them into S3 in bulk."
                )
ap.add_argument("-p", "--frame_prefix", required=False, help="the S3 prefix to upload the extracted frames")
ap.add_argument("-c", "--cleanup_files", required=False, default=True,
                help="whether to automatically clean up the files in the end. If the frames were not uploaded to S3, they will be kept on local disk even if this is set to true ")

ap.add_argument("-pp", "--video_preview_prefix", required=False, default="previews/video/",
                help="the S3 prefix to upload the video preview/visualization. default is previews/video/")


def video_to_frames(video, output_base_dir):
    """
    Convert the videos we took to images and generate the file names unique with frame indexes e.g. 'video_name_000001.jpg'
    :param video: path to the video file on local disk
    :param output_base_dir: the base directory the frames will be saved in
    :return: the directory created that contains extracted frames
    """
    # extract frames from a video and save to directory with the name of the video and file name 'video_name_x.jpg' where
    # x is the frame index
    vidcap = cv2.VideoCapture(video)
    count = 0
    filename = os.path.split(video)[1]
    prefix = os.path.splitext(filename)[0]
    frame_sub_dir = os.path.join(output_base_dir, prefix)
    os.mkdir(frame_sub_dir)
    logger.info("created {} folder for frames".format(frame_sub_dir))
    start = time.time()
    while vidcap.isOpened():
        success, image = vidcap.read()
        if success:
            # Add padding to the frame index. e.g. 1 -> 000001, 10 -> 000010 etc.
            image_name = prefix + '_{0:06d}.jpg'.format(count)
            cv2.imwrite(os.path.join(frame_sub_dir, image_name), image)
            count += 1
            if count % REPORT_STATUS == 0:
                logger.info("extracted {} frames. ".format(count))
                logger.info("took {:10.4f} seconds to extract {} frames".format(time.time() - start, REPORT_STATUS))
                start = time.time()
        else:
            break
    cv2.destroyAllWindows()
    vidcap.release()
    logger.info("written {} frames for {}".format(count, filename))
    return frame_sub_dir


def get_frame_rate(video):
    """ Get the frame rate for the video (frames per second) """

    video = cv2.VideoCapture(video)

    # Find OpenCV version
    (major_ver, minor_ver, subminor_ver) = (cv2.__version__).split('.')

    # With webcam get(CV_CAP_PROP_FPS) does not work.
    # Let's see for ourselves.

    if int(major_ver) < 3:
        fps = video.get(cv2.cv.CV_CAP_PROP_FPS)
        logger.info("Frames per second using video.get(cv2.cv.CV_CAP_PROP_FPS): {0}".format(fps))
    else:
        fps = video.get(cv2.CAP_PROP_FPS)
        logger.info("Frames per second using video.get(cv2.CAP_PROP_FPS) : {0}".format(fps))

    cv2.destroyAllWindows()
    video.release()
    return fps


def sample_frames(frame_dir, fps, visualize_sample_rate):
    """
    Sample frames every X seconds, resize the frame and add it to an numpy array
    :param frame_dir: directory path containing the frames
    :param fps: frame rate of the video
    :return: numpy array of the sampled frames
    """
    visualize_every_x_frames = visualize_sample_rate * int(fps)
    sampled_frames = np.empty((0, 3, IMG_DIM, IMG_DIM), dtype=np.float32)  # B, C, H, W
    i = 0
    for file in sorted(os.listdir(frame_dir)):
        if i % visualize_every_x_frames == 0:
            img = skimage.img_as_float(skimage.io.imread(os.path.join(frame_dir, file))).astype(np.float32)
            img = skimage.transform.resize(img, (IMG_DIM, IMG_DIM))  # H, W, C
            img = img.swapaxes(1, 2).swapaxes(0, 1)  # C, H, W
            sampled_frames = np.append(sampled_frames, np.array([img]), axis=0)
        i += 1
    logger.debug("total number of frames: {}".format(i))
    return sampled_frames


def generate_preview_image(fps, frame_dir, video_name, visualize_sample_rate, working_dir):
    """
    first sample frames every X seconds, resize them ,then
    concatenate sampled images into one image using torchvision's util functions
    :param fps: frame rate of the video
    :param frame_dir: directory path containing the frames
    :param video_name: name of the video
    :param visualize_sample_rate how frequent (in seconds) to sample the frames for the preview
    :param working_dir directory to save the preview
    :return: name of the preview image generated
    """
    sampled_frames = sample_frames(frame_dir, fps, visualize_sample_rate)
    grid = (torchvision.utils.make_grid(torch.from_numpy(sampled_frames)))
    preview_file_name = video_name.split('.')[0] + "-preview.png"
    torchvision.utils.save_image(grid, os.path.join(working_dir, preview_file_name))
    return preview_file_name


def load_data_to_s3(frame_dir, preview_file_name, s3_bucket, frame_prefix, upload_frames, video_preview_prefix,
                    working_dir):
    """
    Upload the extracted frames and the preview image to S3
    :param frame_dir: directory path containing the frames
    :param preview_file_name: preview image generated
    :param s3_bucket s3 bucket to upload to
    :param frame_prefix s3 prefix to upload frames to
    :param upload_frames whether to upload frames to S3
    :param video_preview_prefix s3 prefix to upload video preview to
    :return: None
    """
    if upload_frames:
        count = 0
        frames_s3_prefix = frame_prefix + frame_dir.split('/')[-1]
        start = time.time()
        for frame in os.listdir(frame_dir):
            # this will upload the frame in vid_a/vid_a_000001.jpg to s3://bucket/frame-prefix/vid_a/vid_a_000001.jpg
            frame_local_path =  os.path.join(frame_dir, frame)
            frame_s3_key = "{}/{}".format(frames_s3_prefix, frame)
            s3.Bucket(s3_bucket).upload_file(frame_local_path, frame_s3_key)
            count += 1
            if count % REPORT_STATUS == 0:
                logger.info("uploaded {} frames. ".format(count))
                logger.info("took {:10.4f} seconds to upload {} frames".format(time.time() - start, REPORT_STATUS))
                start = time.time()
        logger.info("uploaded {} frames to s3://{}/{}".format(count, s3_bucket, frames_s3_prefix))

    if preview_file_name is not None:
        preview_file_s3_key = video_preview_prefix + preview_file_name
        s3.Bucket(s3_bucket).upload_file(os.path.join(working_dir, preview_file_name), preview_file_s3_key)
        logger.info("uploaded preview to s3://{}/{}".format(s3_bucket, preview_file_s3_key))


def clean_up_local_files(frame_dir, video_name, upload_frames):
    if upload_frames:
        shutil.rmtree(frame_dir)
        logger.info("deleted folder {}".format(frame_dir))
    # since the video was downloaded from s3, it's safe to delete it as the copy on S3 still exists.
    os.remove(video_name)
    logger.info("deleting video {}".format(video_name))


def process_video(s3_bucket, s3_key, output_s3_bucket, working_dir, upload_frames, frame_prefix, visualize_frames, visualize_sample_rate,
                  video_preview_prefix, clean_up_files):
    start = time.time()
    logger.info("Start processing {}".format(s3_key))
    video_name = s3_key.split('/')[-1]
    s3.Bucket(s3_bucket).download_file(s3_key, video_name)
    fps = get_frame_rate(video_name)
    frame_dir = video_to_frames(video_name, working_dir)
    logger.info("Finished converting video to frames. Took {:10.4f} seconds".format(time.time() - start))

    start = time.time()
    if visualize_frames:
        preview_file_name = generate_preview_image(fps, frame_dir, video_name, visualize_sample_rate, working_dir)

    logger.info("Stored preview at {}. took {:10.4f} seconds.".format(os.path.join(working_dir, preview_file_name),
                                                                      time.time() - start))
    start = time.time()
    load_data_to_s3(frame_dir, preview_file_name, output_s3_bucket, frame_prefix, upload_frames, video_preview_prefix,
                    working_dir)
    logger.info("finished uploading. took {:10.4f} seconds.".format(time.time() - start))

    if clean_up_files:
        clean_up_local_files(frame_dir, video_name, upload_frames)

    if not upload_frames:
        print("The frames are stored at {}. You can use tools like s3 sync to upload them to S3. ".format(frame_dir))


def list_videos(s3_bucket, s3_prefix):
    object_iterator = s3.Bucket(s3_bucket).objects.filter(
        Prefix=s3_prefix
    )
    return object_iterator


def main():
    args = vars(ap.parse_args())
    s3_key = args["video_s3_key"]
    s3_bucket = args["video_s3_bucket"]
    logger.info("video to convert: s3://{}/{}".format(s3_bucket, s3_key))

    output_s3_bucket = args["output_s3_bucket"]
    working_directory = args["working_directory"]
    if not os.path.isdir(working_directory):
        ap.error('--working_directory must be an existing directory')

    logger.info("storing files at: {}".format(working_directory))

    upload_frames = args["upload_frames"]
    frame_prefix = args["frame_prefix"]
    logger.info("upload frames to S3: {}".format(upload_frames))
    if upload_frames:
        if frame_prefix is None:
            ap.error('--frame_prefix must be given if upload_frames is selected')
        else:
            if not frame_prefix.endswith("/"):
                frame_prefix += "/"
            logger.info("Will upload frames to s3://{}/{}".format(s3_bucket, frame_prefix))

    visualize_frames = args["visualize_video"]
    visualize_sample_rate = args["visualize_sample_rate"]
    video_preview_prefix = args["video_preview_prefix"]
    if not video_preview_prefix.endswith("/"):
        video_preview_prefix += "/"

    if visualize_frames:
        logger.info("Will generate visualization for video sampling every {} seconds and upload to s3://{}/{}".format(
            visualize_sample_rate, s3_bucket, video_preview_prefix))

    cleanup_files = args["cleanup_files"]

    process_video(s3_bucket, s3_key, output_s3_bucket, working_directory, upload_frames, frame_prefix, visualize_frames,
                  visualize_sample_rate, video_preview_prefix, cleanup_files)


if __name__ == "__main__":
    main()
