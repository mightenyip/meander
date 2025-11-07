from xml.etree import ElementTree as ET
tree = ET.parse("samples/test_script.fdx")
root = tree.getroot()
print([child.tag for child in root.iter("Paragraph")][:20])

for paragraph in root.iter("Paragraph"):
    p_type = paragraph.attrib.get("Type")
    text = paragraph.findtext("Text")  # optional preview
    print(p_type, text)
    #break  # remove once it works