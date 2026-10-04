{
 "patcher": {
  "fileversion": 1,
  "appversion": {
   "major": 8,
   "minor": 6,
   "revision": 0,
   "architecture": "x64",
   "modernui": 1
  },
  "classnamespace": "box",
  "rect": [
   80.0,
   80.0,
   1040.0,
   640.0
  ],
  "bglocked": 0,
  "openinpresentation": 0,
  "default_fontsize": 12.0,
  "default_fontface": 0,
  "default_fontname": "Arial",
  "gridonopen": 1,
  "gridsize": [
   15.0,
   15.0
  ],
  "boxes": [
   {
    "box": {
     "id": "obj-1",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      20.0,
      10.0,
      600.0,
      20.0
     ],
     "text": "Sonify OSC receiver - TouchDesigner -> UDP 9000 (Oscport). Max MIDI Effect 안에 붙여넣기"
    }
   },
   {
    "box": {
     "id": "obj-2",
     "maxclass": "number",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      20.0,
      40.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0
    }
   },
   {
    "box": {
     "id": "obj-3",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 1,
     "patching_rect": [
      90.0,
      40.0,
      100.0,
      22.0
     ],
     "outlettype": [
      ""
     ],
     "text": "prepend port"
    }
   },
   {
    "box": {
     "id": "obj-4",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 1,
     "patching_rect": [
      20.0,
      65.0,
      107.0,
      22.0
     ],
     "outlettype": [
      ""
     ],
     "text": "loadmess 9000"
    }
   },
   {
    "box": {
     "id": "obj-5",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 1,
     "patching_rect": [
      20.0,
      100.0,
      121.0,
      22.0
     ],
     "outlettype": [
      ""
     ],
     "text": "udpreceive 9000"
    }
   },
   {
    "box": {
     "id": "obj-6",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 13,
     "patching_rect": [
      20.0,
      140.0,
      900.0,
      22.0
     ],
     "outlettype": [
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      "",
      ""
     ],
     "text": "route /sonify/scan/trig /sonify/scan/bandsn /sonify/scan/lumn /sonify/scan/centroidn /sonify/scan/hue /sonify/scan/edgen /sonify/scan/note /sonify/feed1/zs /sonify/feed2/zs /sonify/feed3/zs /sonify/feed1/act /sonify/iss/latn"
    }
   },
   {
    "box": {
     "id": "obj-7",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      20.0,
      180.0,
      320.0,
      20.0
     ],
     "text": "/scan/trig = band note vel -> MIDI note"
    }
   },
   {
    "box": {
     "id": "obj-8",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 3,
     "patching_rect": [
      20.0,
      205.0,
      107.0,
      22.0
     ],
     "outlettype": [
      "int",
      "int",
      "float"
     ],
     "text": "unpack 0 0 0."
    }
   },
   {
    "box": {
     "id": "obj-9",
     "maxclass": "newobj",
     "numinlets": 2,
     "numoutlets": 1,
     "patching_rect": [
      120.0,
      235.0,
      58.0,
      22.0
     ],
     "outlettype": [
      ""
     ],
     "text": "* 127."
    }
   },
   {
    "box": {
     "id": "obj-10",
     "maxclass": "newobj",
     "numinlets": 3,
     "numoutlets": 2,
     "patching_rect": [
      20.0,
      265.0,
      128.0,
      22.0
     ],
     "outlettype": [
      "float",
      "float"
     ],
     "text": "makenote 100 250"
    }
   },
   {
    "box": {
     "id": "obj-11",
     "maxclass": "newobj",
     "numinlets": 2,
     "numoutlets": 1,
     "patching_rect": [
      20.0,
      295.0,
      72.0,
      22.0
     ],
     "outlettype": [
      ""
     ],
     "text": "pack 0 0"
    }
   },
   {
    "box": {
     "id": "obj-12",
     "maxclass": "newobj",
     "numinlets": 7,
     "numoutlets": 1,
     "patching_rect": [
      20.0,
      325.0,
      86.0,
      22.0
     ],
     "outlettype": [
      "int"
     ],
     "text": "midiformat"
    }
   },
   {
    "box": {
     "id": "obj-13",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      20.0,
      385.0,
      65.0,
      22.0
     ],
     "text": "midiout"
    }
   },
   {
    "box": {
     "id": "obj-14",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 1,
     "patching_rect": [
      120.0,
      355.0,
      58.0,
      22.0
     ],
     "outlettype": [
      "int"
     ],
     "text": "midiin"
    }
   },
   {
    "box": {
     "id": "obj-15",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      170.0,
      355.0,
      260.0,
      20.0
     ],
     "text": "midiin -> midiout: 원래 MIDI 도 통과"
    }
   },
   {
    "box": {
     "id": "obj-16",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      360.0,
      180.0,
      300.0,
      20.0
     ],
     "text": "/scan/bandsn (아래 -> 위 대역 밝기, 0..1)"
    }
   },
   {
    "box": {
     "id": "obj-17",
     "maxclass": "multislider",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      360.0,
      205.0,
      260.0,
      120.0
     ],
     "outlettype": [
      "",
      ""
     ],
     "parameter_enable": 0,
     "size": 24,
     "setminmax": [
      0.0,
      1.0
     ],
     "orientation": 0
    }
   },
   {
    "box": {
     "id": "obj-18",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      205.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-19",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      205.0,
      300.0,
      20.0
     ],
     "text": "/sonify/scan/lumn  밝기 0..1 (음량)"
    }
   },
   {
    "box": {
     "id": "obj-20",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      235.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-21",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      235.0,
      300.0,
      20.0
     ],
     "text": "/sonify/scan/centroidn  밝기 무게중심 0..1 (음높이)"
    }
   },
   {
    "box": {
     "id": "obj-22",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      265.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-23",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      265.0,
      300.0,
      20.0
     ],
     "text": "/sonify/scan/hue  색상 0..1 (음색)"
    }
   },
   {
    "box": {
     "id": "obj-24",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      295.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-25",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      295.0,
      300.0,
      20.0
     ],
     "text": "/sonify/scan/edgen  경계/질감 0..1"
    }
   },
   {
    "box": {
     "id": "obj-26",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      325.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-27",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      325.0,
      300.0,
      20.0
     ],
     "text": "/sonify/scan/note  주 음 (MIDI)"
    }
   },
   {
    "box": {
     "id": "obj-28",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      355.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-29",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      355.0,
      300.0,
      20.0
     ],
     "text": "/sonify/feed1/zs  피드1 위치 -1..1"
    }
   },
   {
    "box": {
     "id": "obj-30",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      385.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-31",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      385.0,
      300.0,
      20.0
     ],
     "text": "/sonify/feed2/zs  피드2 위치 -1..1"
    }
   },
   {
    "box": {
     "id": "obj-32",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      415.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-33",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      415.0,
      300.0,
      20.0
     ],
     "text": "/sonify/feed3/zs  피드3 위치 -1..1"
    }
   },
   {
    "box": {
     "id": "obj-34",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      445.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-35",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      445.0,
      300.0,
      20.0
     ],
     "text": "/sonify/feed1/act  피드1 큰 틱 0..1"
    }
   },
   {
    "box": {
     "id": "obj-36",
     "maxclass": "flonum",
     "numinlets": 1,
     "numoutlets": 2,
     "patching_rect": [
      660.0,
      475.0,
      60.0,
      22.0
     ],
     "outlettype": [
      "",
      "bang"
     ],
     "parameter_enable": 0,
     "format": 6
    }
   },
   {
    "box": {
     "id": "obj-37",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      725.0,
      475.0,
      300.0,
      20.0
     ],
     "text": "/sonify/iss/latn  ISS 위도 -1..1"
    }
   },
   {
    "box": {
     "id": "obj-38",
     "maxclass": "comment",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      660.0,
      520.0,
      340.0,
      20.0
     ],
     "text": "나머지 주소는 오른쪽 끝 출구 (route 의 마지막 출구)"
    }
   },
   {
    "box": {
     "id": "obj-39",
     "maxclass": "newobj",
     "numinlets": 1,
     "numoutlets": 0,
     "patching_rect": [
      660.0,
      545.0,
      142.0,
      22.0
     ],
     "text": "print sonify-other"
    }
   }
  ],
  "lines": [
   {
    "patchline": {
     "source": [
      "obj-2",
      0
     ],
     "destination": [
      "obj-3",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-3",
      0
     ],
     "destination": [
      "obj-5",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-4",
      0
     ],
     "destination": [
      "obj-2",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-5",
      0
     ],
     "destination": [
      "obj-6",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      0
     ],
     "destination": [
      "obj-8",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-8",
      2
     ],
     "destination": [
      "obj-9",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-8",
      1
     ],
     "destination": [
      "obj-10",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-9",
      0
     ],
     "destination": [
      "obj-10",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-10",
      0
     ],
     "destination": [
      "obj-11",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-10",
      1
     ],
     "destination": [
      "obj-11",
      1
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-11",
      0
     ],
     "destination": [
      "obj-12",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-12",
      0
     ],
     "destination": [
      "obj-13",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-14",
      0
     ],
     "destination": [
      "obj-13",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      1
     ],
     "destination": [
      "obj-17",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      2
     ],
     "destination": [
      "obj-18",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      3
     ],
     "destination": [
      "obj-20",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      4
     ],
     "destination": [
      "obj-22",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      5
     ],
     "destination": [
      "obj-24",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      6
     ],
     "destination": [
      "obj-26",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      7
     ],
     "destination": [
      "obj-28",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      8
     ],
     "destination": [
      "obj-30",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      9
     ],
     "destination": [
      "obj-32",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      10
     ],
     "destination": [
      "obj-34",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      11
     ],
     "destination": [
      "obj-36",
      0
     ]
    }
   },
   {
    "patchline": {
     "source": [
      "obj-6",
      12
     ],
     "destination": [
      "obj-39",
      0
     ]
    }
   }
  ]
 }
}