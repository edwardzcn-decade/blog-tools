# -*- coding: utf-8 -*-

import os
import sys
import tempfile
import argparse
import oss2
import json
import shutil
from PIL import Image
from itertools import islice
from oss2.api import Bucket
from pathlib import Path


FLAGS = None

# OSS setting
access_key_id = os.getenv('OSS_TEST_ACCESS_KEY_ID', '')
access_key_secret = os.getenv('OSS_TEST_ACCESS_KEY_SECRET', '')
bucket_name = os.getenv('OSS_TEST_BUCKET', 'eddygallery')
root_path = Path.home()/'eddyblog'
# 以杭州区域为例，Endpoint可以是：
#   http://oss-cn-hangzhou.aliyuncs.com
#   https://oss-cn-hangzhou.aliyuncs.com
# VPC内网Endpoint可以是：
#   http://oss-cn-hangzhou-internal.aliyuncs.com
#   https://oss-cn-hangzhou-internal.aliyuncs.com
internal_endpoint = os.getenv(
    # 'OSS_TEST_ENDPOINT', 'http://oss-cn-shenzhen-internal.aliyuncs.com')
    'OSS_TEST_ENDPOINT', 'http://oss-cn-hangzhou-internal.aliyuncs.com')
public_endpoint = os.getenv(
    # 'OSS_TEST_ENDPOINT', 'http://oss-cn-shenzhen.aliyuncs.com')
    'OSS_TEST_ENDPOINT', 'http://oss-cn-hangzhou.aliyuncs.com')


# 确认上面的参数都填写正确了
for param in (access_key_id, access_key_secret, bucket_name, internal_endpoint, public_endpoint):
    assert '<' not in param, '请设置参数：' + param


def get_bucket_info(b, edp):
    tmp_line = "|"
    tmp_width = 70

    print("".center(tmp_width, "="))
    print("|"+"Here is your bucket info".center(tmp_width-2)+"|")
    print("BASIC".center(tmp_width, "-"))
    # 获取bucket相关信息
    bucket_info = b.get_bucket_info()
    print(tmp_line + ('bucket name: ' +
          bucket_info.name).ljust(tmp_width-2) + tmp_line)
    print(tmp_line + ('storage class: ' +
          bucket_info.storage_class).ljust(tmp_width-2) + tmp_line)
    print(tmp_line + ('creation date: ' +
          bucket_info.creation_date).ljust(tmp_width-2) + tmp_line)
    print(tmp_line + ('oss endpoint: ' + edp).ljust(tmp_width-2) + tmp_line)

    # 查看Bucket的状态
    print("STATUS".center(tmp_width, "-"))
    bucket_stat = b.get_bucket_stat()
    print(tmp_line + ('storage: ' + str(bucket_stat.storage_size_in_bytes) +
          " B").ljust(tmp_width-2) + tmp_line)
    print(tmp_line + ('object count: ' + str(bucket_stat.object_count)
                      ).ljust(tmp_width-2) + tmp_line)
    print(tmp_line + ('multi part upload count: ' +
          str(bucket_stat.multi_part_upload_count)).ljust(tmp_width-2) + tmp_line)
    print("".center(tmp_width, "="))
    print()


def get_image_info(image_file):
    """获取本地图片信息
    :param str image_file: 本地图片
    :return tuple: a 3-tuple(height, width, format).
    """
    im = Image.open(image_file)
    return im.height, im.width, im.format


def check_directory(file_path):
    if file_path[-1] == '/':
        return True
    else:
        return False

def create_dir(path):
    if path.exists():
        # 目录存在 则删除
        shutil.rmtree(path)
    path.mkdir()

def download_and_compress(b: Bucket):
    # list_objects = b.list_objects()
    # print(list_objects)
    tmp_dir_path = ""
    all_plot_groups = []
    tmp_plot_group = {}
    for i, object_info in enumerate(oss2.ObjectIterator(b)):
        # if i > 4:
        #     break
        if check_directory(object_info.key):
            # 尝试新建一个compress 对应目录  或者跳过
            # 记录当前目录的值
            if object_info.key == 'Zcompress/':
                # TODO
                break
            all_plot_groups.append({})
            tmp_plot_group = all_plot_groups[-1]
            print(object_info.key)
            tmp_dir_path = root_path/'tmp/'/object_info.key
            # print(tmp_dir_path)
            Path.mkdir(tmp_dir_path, exist_ok=True)
            tmp_plot_group["name"] = object_info.key.strip('/')
            tmp_plot_group["children"] = []
            # print(tmp_plot_group)
            continue

        else:
            new_pic_name = str(object_info.key)[
                object_info.key.rfind("/")+1:len(object_info.key)]
            if FLAGS.ifdownload:
                # 下载到本地
                process = "style/compress1920"
            # cut the file name
                new_pic_path = Path(tmp_dir_path)/new_pic_name
                result = b.get_object_to_file(
                    object_info.key, new_pic_path, process=process)
                info = get_image_info(new_pic_path)
                tmp_plot_group["children"].append("{width}.{height} {name}".format(
                    width=info[1], height=info[0], name=new_pic_name))
                # debug
                # print(tmp_plot_group["children"])
            else:
                # 不下载到本地，存储在图床 compress目录里
                # TODO 需要更改代码，并且跳过compress目录
                process = "style/compress1920/image/info"
                result = b.get_object(
                    object_info.key, process=process)
                json_content = result.read()
                decoded_json = json.loads(oss2.to_unicode(json_content))
                tmp_plot_group["children"].append("{height}.{width} {name}".format(
                    width=decoded_json['ImageWidth']['value'], 
                    height=decoded_json['ImageHeight']['value'],
                    name=new_pic_name))
                # debug 
                # print(tmp_plot_group["children"])

    with open(root_path/"source"/"photos"/"photos.json", 'w') as outfile:

        print(json.dumps(all_plot_groups))
        json.dump(all_plot_groups, outfile)
        # if i > 10:
        #     break


def percentage(consumed_bytes, total_bytes):
    """进度条回调函数，计算当前完成的百分比

    :param consumed_bytes: 已经上传/下载的数据量
    :param total_bytes: 总数据量
    """
    if total_bytes:
        rate = int(100 * (float(consumed_bytes) / float(total_bytes)))
        print('\r{0}% '.format(rate))
        sys.stdout.flush()


def _prepare_temp_file(content):
    """创建临时文件
    :param content: 文件内容
    :return 文件名
    """
    fd, pathname = tempfile.mkstemp(suffix='exam-progress-')
    os.write(fd, content)
    os.close(fd)
    return pathname


def main():
    # 创建Bucket对象，所有Object相关的接口都可以通过Bucket对象来进行
    if FLAGS.internal:
        bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret), internal_endpoint, bucket_name)
        tmp_endpoint = internal_endpoint
    else:
        bucket = oss2.Bucket(
            oss2.Auth(access_key_id, access_key_secret), public_endpoint, bucket_name)
        tmp_endpoint = public_endpoint

    create_dir(root_path/'tmp/')
    get_bucket_info(bucket, tmp_endpoint)
    download_and_compress(bucket)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-f',
        '--file',
        dest='files',
        action='append',
        default=[],
        help='the file name you want to download!')

    parser.add_argument(
        '-ifdl',
        '--ifdownload',
        default=True,
        dest="ifdownload",
        action="store_true",
        help="If been True, download the compress images to /tmp directory."
    )

    parser.add_argument(
        "-l",
        "--listfiles",
        default=False,
        dest="listFiles",
        action="store_true",
        help="If been True, list the All the files on the oss !")

    parser.add_argument(
        "-o",
        "--outputPath",
        dest="outputPath",
        default="./",
        type=str,
        help="the floder we want to save the files!")

    parser.add_argument(
        "-i",
        "--internal",
        dest="internal",
        default=False,
        action="store_true",
        help="if you using the internal network of aliyun ECS !")

    parser.add_argument(
        "--upload",
        dest="upload",
        default=False,
        action="store_true",
        help="If been used, the mode will be select local files to upload!")

    parser.add_argument(
        "-p",
        "--prefix",
        dest="prefix",
        default=False,
        type=str,
        help="the prefix add to the upload files!")

    parser.add_argument(
        "-d",
        "--directory",
        dest="directory",
        default="",
        type=str,
        help="the directory add to the upload files!")

    FLAGS, unparsed = parser.parse_known_args()

    print(FLAGS)      # print the arguments
    main()
