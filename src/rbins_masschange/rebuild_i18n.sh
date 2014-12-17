#!/usr/bin/env bash
PRODUCTNAME='rbins_masschange'
I18NDOMAIN=$PRODUCTNAME
CWD=$(dirname $0)
cd ${CWD}
CWD=$PWD
export PATH=$CWD/../../../../bin:$CWD/../../bin:$PATH
echo $PATH
i18ndude=$(which i18ndude)
echo "Using ${i18ndude} in ${CWD}"
# Synchronise the .pot with the templates.
${i18ndude} rebuild-pot --pot locales/${PRODUCTNAME}.pot --merge locales/${PRODUCTNAME}-manual.pot --create ${I18NDOMAIN} . ../../../../mars.policy/
# Synchronise the resulting .pot with the .po files
for po in locales/*/LC_MESSAGES/${PRODUCTNAME}.po;do 
    ${i18ndude} sync --pot locales/${PRODUCTNAME}.pot $po
done
