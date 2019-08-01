import os
import json
import shutil
from urllib.parse import urlparse
import boto3
import logging
from botocore.errorfactory import ClientError

s3 = boto3.resource('s3')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def read_manifest_file(file_path):
    with open(file_path, 'r') as f:
        output = [json.loads(line.strip()) for line in f.readlines()]
        return output

def write_manifest_file(lines, file_path):
    num_of_lines = 0
    with open(file_path, 'w') as f:
        for line in lines:
            f.write(json.dumps(line))
            f.write('\n')
            num_of_lines += 1
    return num_of_lines


def create_tmp_dir(tmp_folder):
    if not os.path.exists(tmp_folder):
        os.makedirs(tmp_folder)
    else:
        shutil.rmtree(tmp_folder)
        os.makedirs(tmp_folder)

def exists_in_s3(s3bucket, s3key):
    try:
        s3.meta.client.head_object(Bucket=s3bucket, Key=s3key)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] == '404':
            return False
        else:
            print (e.response["Error"])
            raise e

def download_file(uri, working_dir):
    fname = uri.split('/')[-1]
    image_local_path = os.path.join(working_dir, fname)
    s3_paths = urlparse(uri)
    s3_bucket = s3_paths.netloc
    s3_key = s3_paths.path.lstrip('/')
    s3.Bucket(s3_bucket).download_file(s3_key, image_local_path)
    return image_local_path


def upload_file(image_local_path, s3_bucket, s3_prefix):
    fname = image_local_path.split('/')[-1]
    s3_key = s3_prefix + "/" + fname
    s3.Bucket(s3_bucket).upload_file(image_local_path, s3_prefix + "/" + fname)
    logger.info("wrote to s3://{}/{}".format(s3_bucket, s3_key))
