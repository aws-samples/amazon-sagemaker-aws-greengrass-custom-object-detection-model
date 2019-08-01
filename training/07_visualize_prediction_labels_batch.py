import os
import json
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import logging
import argparse
import numpy as np
from gluoncv.utils import viz
import boto3
import cv2

from urlparse import urlparse  # python 2

# from urllib.parse import urlparse  # python 3


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
s3 = boto3.resource('s3')

# construct the argument parser and parse the arguments
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--image-folder", required=True, help="folder containing images to do inference on")
ap.add_argument("-l", "--label-fname", required=True, help="label file name")
ap.add_argument("-f", "--output-fname", required=True, help="generated pdf file name")
ap.add_argument("-c", "--confidence-filter", required=False, default=0.2, help="confidence filter to use")

COL = 3
MAX_ROW = 5
SHAPE = 512
CLASSES = ['blue box', 'yellow box']


def read_manifest_file(file_path):
    with open(file_path, 'r') as f:
        output = [json.loads(line.strip()) for line in f.readlines()]
        return output


def download_file(uri, working_dir):
    fname = uri.split('/')[-1]
    image_local_path = os.path.join(working_dir, fname)
    s3_paths = urlparse(uri)
    s3_bucket = s3_paths.netloc
    s3_key = s3_paths.path.lstrip('/')
    s3.Bucket(s3_bucket).download_file(s3_key, image_local_path)
    return image_local_path


def title_page(title, pdf):
    '''Create a title page with only text.'''
    plt.figure(figsize=(10, 10), facecolor='white', dpi=100)
    plt.text(0.1, 0.5, s=title, fontsize=20)
    plt.axis('off')
    pdf.savefig()
    plt.close()


def page_loop(page_number, beginning_index, predictions, image_folder, pdf, confidence_filter):
    '''Loop over a single image page of the output pdf.'''

    row = min(MAX_ROW, int((len(predictions) - beginning_index) / COL + 1))
    last_index = min(len(predictions), beginning_index + row * COL)
    logger.info(
        "page number: {}, row number: {}, beginning index: {}, last index: {}".format(page_number, row, beginning_index,
                                                                                      last_index))

    fig, axes = plt.subplots(nrows=row, ncols=COL,
                             figsize=(20, 20),
                             facecolor='white', dpi=100)
    fig.suptitle('Page {}'.format(page_number), fontsize=24)

    for i in range(beginning_index, last_index):
        entry = predictions[i]
        try:

            image_path = os.path.join(image_folder, entry['image'])

            img = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
            # Resize image to fit network input
            # origs = cv2.resize(img, (SHAPE,SHAPE))
            origs = img
            # tensors, origs = yolo_transform.load_test(image_path, short=SHAPE)
            height, width, _c = origs.shape
            labels = np.array(entry['prediction'])

            if (len(entry['prediction']) > 0):
                cid = labels[:, 0]
                score = labels[:, 1]
                bbox = labels[:, range(2, 6)]

                bbox[:, (0, 2)] *= width
                bbox[:, (1, 3)] *= height
            else:
                cid = []
                score = []
                bbox = []
            img_name = entry['image'].split(".")[0]
            if row == 1:
                ax = axes[(i - beginning_index) % COL]
            else:
                ax = axes[int((i - beginning_index) / COL), (i - beginning_index) % COL]
            ax.set_title("{}".format(img_name))
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
            axis = viz.plot_bbox(origs, bbox, score, cid, thresh=confidence_filter,
                                 class_names=CLASSES, ax=ax)
        except:
            logger.error(json.dumps(entry, indent=2))
            raise
    next_page_number = page_number + 1
    next_beginning_index = last_index
    pdf.savefig()
    plt.close()

    return next_page_number, next_beginning_index


def get_ground_truth_labels(s3_uri):
    ground_truth_file = download_file(s3_uri, ".")
    validation_lines = read_manifest_file(ground_truth_file)
    ground_truth_labels = {}
    for line in validation_lines:
        img_name = line["source-ref"].split("/")[-1].split(".")[0]
        annotations = line["bb"]["annotations"]
        number_of_boxes = len(annotations)
        ground_truth_labels[img_name] = {"bb": annotations, "n": number_of_boxes}
    logger.info("read {} lines from {}".format(len(ground_truth_labels), s3_uri))
    return ground_truth_labels


def main():
    args = vars(ap.parse_args())
    image_folder = args["image_folder"]
    output_fname = args["output_fname"]
    label_fname = args['label_fname']
    confidence_filter_score = float(args["confidence_filter"])
    logger.info("doing inference for images in directory: {}".format(image_folder))
    logger.info("confidence filter: {}".format(confidence_filter_score))
    logger.info("output file name: {}".format(output_fname))
    predictions = read_manifest_file(label_fname)
    logger.info("label file name: {}. number of labels: {}".format(label_fname, len(predictions)))

    with PdfPages(output_fname) as pdf:
        title_page('Pig head ground truth labels\n confidence filter: {} \n'.format(confidence_filter_score), pdf)
        next_page_number, next_beginning_index = page_loop(0, 0, predictions, image_folder,
                                                           pdf=pdf,
                                                           confidence_filter=confidence_filter_score
                                                           )

        while next_beginning_index < len(predictions):
            next_page_number, next_beginning_index = page_loop(next_page_number, next_beginning_index, predictions,
                                                               image_folder,
                                                               pdf=pdf,
                                                               confidence_filter=confidence_filter_score
                                                               )


if __name__ == "__main__":
    main()
