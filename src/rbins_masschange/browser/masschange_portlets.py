#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import re
import traceback

import z3c.form
import zope.schema
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from z3c.form.browser.radio import RadioFieldWidget
from z3c.relationfield import RelationValue
from z3c.relationfield.schema import RelationList, RelationChoice
from zope import component, interface
from zope.i18nmessageid import MessageFactory
from zope.intid.interfaces import IIntIds
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary
from zope.component import getUtility, getMultiAdapter

import plone.z3cform.templates
from OFS.CopySupport import CopyError
from Products.Archetypes.interfaces import IBaseContent
from Products.CMFBibliographyAT.interface.content import IBibliographicItem
from Products.CMFCore.interfaces._content import IFolderish
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.utils import base_hasattr
from Products.CMFPlone.utils import safe_unicode
from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile as FiveViewPageTemplateFile
from Products.statusmessages.interfaces import IStatusMessage
from plone import api
from plone.app.dexterity.behaviors.discussion import IAllowDiscussion
from plone.app.dexterity.behaviors.exclfromnav import IExcludeFromNavigation
from plone.app.dexterity.behaviors.metadata import IOwnership
from plone.app.iterate.interfaces import ConflictError
from plone.app.relationfield.behavior import IRelatedItems as BIRelatedItems
from plone.app.textfield.value import RichTextValue
from plone.autoform import directives
from plone.autoform.form import AutoExtensibleForm
from plone.i18n.normalizer import baseNormalize
from plone.uuid.interfaces import IUUID
from rbins_masschange.utils import magicstring
from plone.portlet.static.static import IStaticPortlet
from plone.portlets.interfaces import IPortletManager, IPortletAssignmentMapping

try:
    from plone.app.widgets.interfaces import IWidgetsLayer
    from plone.app.widgets.dx import (RelatedItemsFieldWidget,
                                      AjaxSelectWidget,
                                      RelatedItemsWidget)

    HAS_W = True
except ImportError:
    HAS_W = False
    from plone.formwidget.contenttree import ObjPathSourceBinder

_ = MessageFactory('rbins_masschange')
logger = logging.getLogger('rbins_masschange.masschange')


def make_vocabulary(*items):
    terms = [SimpleTerm(value=value, token=value, title=label)
             for value, label in items]
    return SimpleVocabulary(terms)


def safe_encode(s, coding='utf-8', errors='surrogateescape'):
    """encode str to bytes, with round-tripping "invalid" bytes"""
    if s is None:
        return None
    return s.encode(coding, errors)


class IMassChangePortletsSchema(interface.Interface):
    """Define masschange form fields"""

    if not HAS_W:
        selected_obj_paths = RelationList(
            title=u"Objects to change (leave empty for all Folders and Documents)",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                source=ObjPathSourceBinder()))
    else:
        directives.widget('selected_obj_paths', RelatedItemsWidget)

        selected_obj_paths = RelationList(
            title=u"Objects to change tags (leave empty for all Folders and Documents)",
            required=False,
            default=[],
            value_type=RelationChoice(
                title=u"Related",
                vocabulary="plone.app.vocabularies.Catalog"))

    text_replace_fields = zope.schema.Tuple(
        title=u"Fields to update",
        required=False,
        description=u"Select fields where you want to apply the text replace",
        default=('text',),
        value_type=zope.schema.Choice(
            vocabulary=make_vocabulary(
                (u'text', u"Text body (text)"),
                (u'header', u"Portlet header"),
                (u'footer', u"Portlet footer"),
            )
        ))
    directives.widget(text_replace_fields=CheckBoxFieldWidget)

    text_replace_mode = zope.schema.Choice(
        title=u"Text replacement mode",
        required=False,
        description=u"Select fields where you want to apply the text replace",
        default=u'plain',
        vocabulary=make_vocabulary(
            (u'plain', u"Replace plain text by another one"),
            (u'regexp', u"Replace pattern using regular expression."),
            (u'empty', u"Set text on all empty fields."),
        )
    )
    directives.widget(text_replace_mode=RadioFieldWidget)

    text_replace_source = zope.schema.TextLine(
        title=u"Text / pattern to replace",
        description=u"Set the plain text or regular expression to replace. If you choose 'set text on all empty fields', leave this field empty.",
        required=False,
    )

    text_replace_destination = zope.schema.TextLine(
        title=u"Replacement text / pattern",
        required=False,
        description=u"In regular expression mode, you can use \\1, \\2, etc. here to get pattern groups",
    )


def safe_encode(s, coding='utf-8', errors='surrogateescape'):
    """encode str to bytes, with round-tripping "invalid" bytes"""
    if type(s) == str:
        return s
    elif s is None:
        return None
    else:
        return s.encode(coding, errors)


class MassChangePortletsForm(AutoExtensibleForm, z3c.form.form.Form):
    """ A form to output a HTML masschange from chosen parameters """
    schema = IMassChangePortletsSchema
    ignoreContext = True
    status = ""
    logs = None

    def replace_portlet_text(self, context, mode, fields, source, destination):
        def get_new_value(current_value):
            if type(current_value) == str:
                s = safe_encode(source)
                d = safe_encode(destination)
            else:
                s = safe_unicode(source)
                d = safe_unicode(destination)

            if mode == 'plain':
                new_value = current_value.replace(s, d)
            elif mode == 'regexp':
                new_value = re.sub(s, d, current_value)
            elif mode == 'empty':
                new_value = current_value if current_value else d
            else:
                raise ValueError("Unhandled option for text_replace_mode: %s" % mode)
            return new_value

        changed = False
        for manager_name in [
            "plone.leftcolumn",
            "plone.rightcolumn",
            "ContentWellPortlets.InHeaderPortletManager1",
            "ContentWellPortlets.InHeaderPortletManager2",
            "ContentWellPortlets.InHeaderPortletManager3",
            "ContentWellPortlets.InHeaderPortletManager4",
            "ContentWellPortlets.InHeaderPortletManager5",
            "ContentWellPortlets.InHeaderPortletManager6",
            "ContentWellPortlets.AbovePortletManager1",
            "ContentWellPortlets.AbovePortletManager2",
            "ContentWellPortlets.AbovePortletManager3",
            "ContentWellPortlets.AbovePortletManager4",
            "ContentWellPortlets.AbovePortletManager5",
            "ContentWellPortlets.AbovePortletManager6",
            "ContentWellPortlets.BelowPortletManager1",
            "ContentWellPortlets.BelowPortletManager2",
            "ContentWellPortlets.BelowPortletManager3",
            "ContentWellPortlets.BelowPortletManager4",
            "ContentWellPortlets.BelowPortletManager5",
            "ContentWellPortlets.BelowPortletManager6",
            "ContentWellPortlets.FooterPortletManager1",
            "ContentWellPortlets.FooterPortletManager2",
            "ContentWellPortlets.FooterPortletManager3",
            "ContentWellPortlets.FooterPortletManager4",
            "ContentWellPortlets.FooterPortletManager5",
            "ContentWellPortlets.FooterPortletManager6",
        ]:
            try:
                manager = getUtility(IPortletManager, name=manager_name, context=context)
            except Exception as e:
                continue
            mapping = getMultiAdapter((context, manager), IPortletAssignmentMapping)

            for id, assignment in mapping.items():
                if IStaticPortlet.providedBy(assignment):
                    for field in fields:
                        text = getattr(assignment, field, None)
                        if text is None:
                            continue
                        new_text = get_new_value(text)
                        if new_text != text:
                            changed = True
                            setattr(assignment, field, new_text)

        return changed

    def update(self):
        psson = 'paths'
        sson = 'selected_obj_paths'
        obs = []
        pssonvalues = self.request.form.get(psson, [])
        ssonvalues = self.request.form.get(sson, [])
        tp = self.request.form.get('orig_template', '')
        # coming from folder_contents with filters and collections
        if (tp in ['folder_contents'] and
                isinstance(pssonvalues, list) and pssonvalues and
                isinstance(ssonvalues, list) and ssonvalues):
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
        else:
            # coming from folder_contents with filters
            if isinstance(pssonvalues, list) and pssonvalues:
                for item in pssonvalues:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
            # coming from other cases
            elif sson in self.request.form:
                for item in self.request.form[sson]:
                    try:
                        v = str(item)
                        self.context.restrictedTraverse(v)
                        obs.append(item)
                    except ConflictError:
                        raise
                    except Exception:
                        pass
        ret = super(MassChangePortletsForm, self).update()
        if obs:
            if HAS_W:
                portal = getToolByName(self.context,
                                       'portal_url').getPortalObject()
                uids = []
                for i in obs:
                    try:
                        uids.append(IUUID(portal.restrictedTraverse(i)))
                    except ConflictError:
                        raise
                    except Exception:
                        continue
                obs = self.widgets[sson].separator.join(uids)
            self.request.form[u'form.widgets.%s' % sson] = obs
            self.widgets[sson].update()
        return ret

    @z3c.form.button.buttonAndHandler(_(u'Make Changes'), name='masschange')
    def masschange(self, action):
        # already passed (updateWidget called twice
        self.logs, ilogs = [], []
        if self.status != '':
            return
        data, errors = self.extractData()
        if errors:
            self.status = "Please correct errors"
            return
        portal_types = getToolByName(self.context, 'portal_types')
        portal_catalog = getToolByName(self.context, 'portal_catalog')
        site = getToolByName(self.context, 'portal_url').getPortalObject()

        items = data['selected_obj_paths']

        if not items:
            items = []
            items.append(site)
            brains = portal_catalog.unrestrictedSearchResults(portal_type=['Folder', 'Document'])
            for brain in brains:
                obj = brain.getObject()
                items.append(obj)

        for item in items:
            changed = False
            ppath = '/'.join(item.getPhysicalPath())

            if self.replace_portlet_text(
                    context=item,
                    mode=data['text_replace_mode'],
                    fields=data['text_replace_fields'],
                    destination=data['text_replace_destination'],
                    source=data['text_replace_source']):
                changed = True

            if changed:
                ilogs.append('<li><a href="%s" target="_new">%s</a> portlets changed</li>\n' % (
                    ppath, item.absolute_url()))
        if ilogs:
            ilogs.insert(0, u"<strong>MassChange complete</strong>")
            ilogs.insert(0, u"<ul>")
            ilogs.append('</ul>')
        self.logs.extend(ilogs)
        self.logs = '\n'.join(self.logs)


masschangeportlets_form_frame = plone.z3cform.layout.wrap_form(
    MassChangePortletsForm,
    index=FiveViewPageTemplateFile("masschange_portlets.pt"))
