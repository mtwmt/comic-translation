import numpy as np
from PIL import Image

from src.offline.recovery import recover_missed_text


def page():
    image = Image.new("RGB", (400, 600), "white")
    pixels = np.asarray(image).copy()
    pixels[100:200, 300:340] = 0
    return Image.fromarray(pixels)


def box(x1, y1, x2, y2):
    return np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])


def test_missed_text_is_added_with_its_ink_mask():
    detections, mask = recover_missed_text(page(), [], np.zeros((600, 400), bool), [(box(295, 95, 345, 205), .7)])
    assert len(detections) == 1
    assert mask[150, 320] and not mask[10, 10]


def test_already_detected_tiny_and_blank_boxes_are_ignored():
    known = [(box(290, 90, 350, 210), .9)]
    extra = [(box(295, 95, 345, 205), .7), (box(10, 10, 15, 15), .9), (box(100, 300, 200, 400), .9)]
    detections, mask = recover_missed_text(page(), known, np.zeros((600, 400), bool), extra)
    assert detections == known and not mask.any()


def test_split_pieces_of_one_block_are_merged():
    extra = [(box(295, 95, 345, 150), .7), (box(295, 140, 345, 205), .6)]
    detections, _ = recover_missed_text(page(), [], np.zeros((600, 400), bool), extra)
    assert len(detections) == 1
    # The ink is x 300-339, y 100-199; the box hugs it, not the padded detector box.
    low, high = detections[0][0].min(axis=0), detections[0][0].max(axis=0)
    assert 295 <= low[0] <= 300 and 95 <= low[1] <= 100
    assert 339 <= high[0] <= 344 and 199 <= high[1] <= 204


def test_box_hugs_thick_lettering_not_thin_outline():
    image = np.full((600, 400, 3), 255, np.uint8)
    image[100:200, 150:200] = 0
    image[90:92, 100:300] = 0   # thin balloon outline inside the detector box
    detections, _ = recover_missed_text(Image.fromarray(image), [], np.zeros((600, 400), bool),
                                        [(box(95, 85, 305, 210), .7)])
    low, high = detections[0][0].min(axis=0), detections[0][0].max(axis=0)
    assert low[0] >= 140 and high[0] <= 210 and low[1] >= 90


def test_hearts_and_specks_inside_the_title_are_cleaned_but_edge_ink_is_kept():
    image = np.full((600, 400, 3), 255, np.uint8)
    image[100:300, 150:200] = 0          # lettering
    image[302:305, 160:168] = 0          # small mark just below it (heart / wave)
    image[250:252, 202:204] = 0          # stray speck beside it
    image[:, 330:334] = 0                # long outline crossing the window edge
    detections, mask = recover_missed_text(Image.fromarray(image), [], np.zeros((600, 400), bool),
                                           [(box(140, 90, 340, 330), .7)])
    assert detections and mask[200, 170] and mask[303, 163] and mask[250, 202]
    assert not mask[200, 331]


def test_lone_glyph_of_a_sound_effect_grows_along_its_column_but_not_into_borders():
    image = np.full((1600, 1200, 3), 255, np.uint8)
    for top in (100, 220, 340):            # three stacked glyphs, 60 px apart in a column
        image[top:top + 80, 200:280] = 0
        image[top + 20:top + 60, 220:260] = 255
    image[60:68, :] = 0                    # a long panel border above them
    image[:, 330:338] = 0                  # and one beside them
    detections, mask = recover_missed_text(Image.fromarray(image), [], np.zeros((1600, 1200), bool),
                                           [(box(190, 90, 290, 190), .7)])
    assert len(detections) == 1
    low, high = detections[0][0].min(axis=0), detections[0][0].max(axis=0)
    assert high[1] >= 410 and low[1] >= 90          # reached the last glyph
    assert low[0] >= 190 and high[0] <= 290          # stayed in the column
    assert not mask[64, 100] and not mask[400, 334]  # borders untouched
