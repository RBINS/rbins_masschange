#!/usr/bin/env python
# -*- coding: utf-8 -*-
__docformat__ = 'restructuredtext en'
import traceback
from plone.uuid.interfaces import IUUID
from Products.CMFCore.utils import getToolByName
import zope.schema
from zope import component, interface
from zope.intid.interfaces import IIntIds
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile as FiveViewPageTemplateFile
import logging

from zope.schema.vocabulary import SimpleVocabulary
from zope.schema.vocabulary import SimpleTerm

import z3c.form
from z3c.relationfield import RelationValue

from zope.interface import invariant, Invalid

import plone.app.z3cform
import plone.z3cform.templates
from z3c.form.interfaces import ActionExecutionError, WidgetActionExecutionError
from plone.autoform.form import AutoExtensibleForm
from plone.app.relationfield.behavior import IRelatedItems as BIRelatedItems
from collective.z3cform.keywordwidget.widget import (
    KeywordFieldWidget,
    InAndOutKeywordFieldWidget,
    InAndOutKeywordWidget)
from collective.z3cform.keywordwidget.field import Keywords

from z3c.relationfield.schema import RelationList, Relation, RelationChoice

from plone.autoform import directives
from zope.i18nmessageid import MessageFactory


try:
    from plone.app.widgets.dx import (RelatedItemsFieldWidget,
                                      RelatedItemsWidget)
    HAS_W = True
except ImportError:
    HAS_W = False
    from plone.formwidget.contenttree import ObjPathSourceBinder

_ = MessageFactory('rbins_masschange')
logger = logging.getLogger('rbins_masschange.masschange')

def make_terms(items):
    """ Create zope.schema terms for vocab from tuples """
    terms = [SimpleTerm(value=pair[0], token=pair[0], title=pair[1])
             for pair in items]
    return terms


output_type_vocab = SimpleVocabulary(
    make_terms([("list", "Patient list"),
                ("summary", "Summary")]))


class IMassChangeSchema(interface.Interface):
    """Define masschange form fields"""
    #directives.widget('local_keywords', InAndOutKeywordWidget)

    if not HAS_W:
        selected_obj_paths = RelationList(
            title=u"Objects to change tags",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                source=ObjPathSourceBinder()))

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                source=ObjPathSourceBinder()))
    else:
        directives.widget('selected_obj_paths', RelatedItemsWidget)
        directives.widget('related_obj_paths', RelatedItemsWidget)

        selected_obj_paths = RelationList(
            title=u"Objects to change tags",
            required=True,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                vocabulary="plone.app.vocabularies.Catalog"))

        related_obj_paths = RelationList(
            title=u"Objects to link with",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Link with those objects",
                vocabulary="plone.app.vocabularies.Catalog")) 

    local_keywords = zope.schema.List(
        title=u"Keywords from this folder",
        required=False,
        description=u"Keyword (local)",
        value_type=zope.schema.Choice(
            vocabulary='rbins_masschange.localKeywords'))

    keywords = Keywords(
        title=u"keywords",
        description=u"Keyword (general)",
        required=False,
        index_name='Subject')

    manual_keywords = zope.schema.List(
        title=u"Keywords to add", required=False,
        value_type=(zope.schema.TextLine()))


def default_keywords(self):
    return self.view.old_keywords[:]


class MassChangeForm(AutoExtensibleForm, z3c.form.form.Form):
    """ A form to output a HTML masschange from chosen parameters """
    schema = IMassChangeSchema
    ignoreContext = True

    def update(self):
        self.old_keywords = []
        try:
            self.old_keywords = [a for a in self.context.Subject()]
        except:
            pass
        sson = 'selected_obj_paths'
        obs = []
        if sson in self.request.form:
            for item in self.request.form[sson]:
                try:
                    v = str(item)
                    self.context.restrictedTraverse(v)
                    obs.append(item)
                except:
                    pass
        ret = super(MassChangeForm, self).update()
        if obs:
            if HAS_W:
                portal = getToolByName(self.context,
                                       'portal_url').getPortalObject()
                uids = []
                for i in obs:
                    try:
                        uids.append(IUUID(portal.restrictedTraverse(obs[0])))
                    except Exception:
                        continue
                obs = self.widgets[sson].separator.join(uids)
            self.request.form[u'form.widgets.%s' % sson] = obs
            self.widgets[sson].update()
        return ret

    @z3c.form.button.buttonAndHandler(_(u'Make Changes'), name='masschange')
    def masschange(self, action):
        # already passed (updateWidget called twice
        if self.status != '':
            return
        data, errors = self.extractData()
        if errors:
            self.status = "Please correct errors"
            return
        keywords = []
        for k in 'keywords', 'local_keywords', 'manual_keywords':
            d = data.get(k, None)
            if d:
                [keywords.append(i)
                 for i in d
                 if i not in keywords]
        keywords.sort()
        self.logs, ilogs = [], []
        for item in data['selected_obj_paths']:
            ppath = '/'.join(item.getPhysicalPath())
            changed = False
            if data['related_obj_paths']:
                # item support related items
                related = []
                # archetypes
                try:
                    related = item.getRelatedItems()

                    def additem(xxx, related):
                        changed = False
                        xxx = [x for x in xxx if x not in related]
                        if xxx:
                            item.setRelatedItems(related + xxx)
                            changed = True
                        return changed
                except Exception:
                    additem = None
                # dexterity
                if not additem:
                    try:
                        related = BIRelatedItems(item).relatedItems

                        def additem(xxx, related):
                            changed = False
                            xxx = [x for x in xxx if x not in related]
                            if True or xxx:
                                intids = component.getUtility(IIntIds)
                                BIRelatedItems(item).relatedItems = (
                                    [RelationValue(intids.getId(obj)) 
                                     for obj in (related + xxx)])
                                #BIRelatedItems(item).relatedItems = (
                                #    [RelationValue(IUUID(obj)) 
                                #     for obj in (related + xxx)])
                                changed = True
                            return changed
                    except Exception:
                        additem = None
                if additem is not None:
                    changed = additem(data['related_obj_paths'], related)
            try:
                oldk = [a for a in self.context.Subject()]
            except:
                oldk = []
            oldk.sort()
            if keywords != oldk:
                try:
                    try:
                        item.setSubject(keywords)
                        changed = True
                    except AttributeError:
                        item.subject = keywords
                        changed = True
                except Exception:
                    trace = traceback.format_exc()
                    msg = ('<li>%s %s: cant change keywords '
                           '<br/><pre>%s</pre>\n</li>') % (
                               ppath, keywords, trace)
                    logger.error(msg)
                    ilogs.append(msg)
            if changed:
                ilogs.append('<li>%s changed</li>\n' % ppath)
                item.reindexObject()
        if ilogs:
            ilogs.insert(0, u"<strong>MassChange complete</strong>")
            ilogs.insert(0, u"<ul>")
            ilogs.append('</ul>')
        self.logs.extend(ilogs)
        self.logs = '\n'.join(self.logs)


for k in ('keywords', 'local_keywords',):
    component.provideAdapter(
        z3c.form.widget.ComputedWidgetAttribute(
            default_keywords,
            field=IMassChangeSchema[k],
            view=MassChangeForm),
        name="default")


masschange_form_frame = plone.z3cform.layout.wrap_form(
    MassChangeForm,
    index=FiveViewPageTemplateFile("masschange.pt"))

# vim:set et sts=4 ts=4 tw=80:
