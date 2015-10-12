#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from plone.theme.interfaces import IDefaultPloneLayer


class ILayer(IDefaultPloneLayer):
    """Marker interface that defines a Zope 3 browser layer."""

# vim:set et sts=4 ts=4 tw=80:
