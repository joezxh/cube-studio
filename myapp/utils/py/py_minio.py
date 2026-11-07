# -*- coding: utf-8 -*-
"""minio 访问封装（企业版 #8 artifact 回收）。

自包含模块：顶层仅标准库，minio SDK 在 make_minio_client 内惰性 import；
remove_object_prefix 接受注入的 client（duck-type），测试无需 minio 依赖。
"""


def make_minio_client(conf_get):
    """conf_get: dict.get 式可调用（调用方传 myapp 的 conf.get）。

    凭证 conf 化：MINIO_ACCESS_KEY / MINIO_SECRET_KEY，
    缺省值沿用现网硬编码值保证行为兼容。
    """
    from minio import Minio
    return Minio(
        endpoint=conf_get('MINIO_HOST', 'minio.kubeflow:9000'),
        access_key=conf_get('MINIO_ACCESS_KEY', 'minio'),
        secret_key=conf_get('MINIO_SECRET_KEY', 'minio123'),
        secure=False,
    )


def remove_object_prefix(client, bucket, prefix):
    """删除 bucket 内指定前缀的全部对象。

    返回 (removed_count, errors)；单对象失败记录后继续，
    list 整体失败返回 (0, [msg])。不抛出——调用方仅 logging。
    """
    try:
        objects = list(client.list_objects(bucket, prefix=prefix, recursive=True))
    except Exception as e:
        return 0, [str(e)]
    removed, errors = 0, []
    for obj in objects:
        try:
            client.remove_object(bucket, obj.object_name)
            removed += 1
        except Exception as e:
            errors.append('%s: %s' % (obj.object_name, e))
    return removed, errors
