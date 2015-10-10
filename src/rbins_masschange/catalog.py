#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from zope.component import adapts
from zope.interface import implements
from plone.indexer import indexer
from plone.dexterity.interfaces import IDexterityItem
from plone.app.dexterity.behaviors.metadata import IOwnership

from Products.Archetypes.interfaces.base import IBaseContent
from collective import dexteritytextindexer
from rbins_masschange.utils import magicstring


def _Contributors(item):
    try:
        ownership = IOwnership(item)
        ctbtrs = ownership.contributors
    except TypeError:
        try:
            ctbtrs = item.Contributors
        except AttributeError:
            ctbtrs = []
    return [magicstring(a) for a in ctbtrs]


AContributors = indexer(IBaseContent)(_Contributors)
BContributors = indexer(IDexterityItem)(_Contributors)


def _ZContributors(item):
    return " ".join(_Contributors(item))


AZContributors = indexer(IBaseContent)(_ZContributors)
BZContributors = indexer(IDexterityItem)(_ZContributors)
# vim:set et sts=4 ts=4 tw=80:
