# Blender Scene Schema v1.0 — Phase 2 Specification

**Status:** 🟡 **SPECIFICATION READY FOR IMPLEMENTATION**  
**Version:** 1.0.0  
**Date:** 2026-09-24

---

## Overview

This document defines the JSON schema for 3D scenes rendered by Blender in Phase 2 of the Video Producer plugin. The schema bridges:

- **Input:** Narration text + Storyboard JSON (from Phase 1)
- **Processing:** Scene Builder generates .blend file
- **Output:** MP4 video (rendered by Blender)

---

## Root Schema

```json
{
  "scene_id": "string",           // Unique scene identifier
  "version": "1.0",               // Schema version
  "title": "string",              // Human-readable title
  "description": "string",        // Optional description
  "duration": 30.0,               // Total duration in seconds
  "framerate": 30,                // Frames per second (30 or 60)
  "resolution": {                 // Output resolution
    "width": 1920,
    "height": 1080
  },
  "render_settings": {            // Blender render config
    "engine": "CYCLES",           // CYCLES | EEVEE
    "samples": 100,               // Quality: 50-300
    "use_gpu": true,              // GPU acceleration
    "denoiser": "OPENIMAGEDENOISE" // Noise reduction
  },
  "world": {                      // Scene environment
    "background_color": [0.1, 0.1, 0.1],  // RGB 0-1
    "hdri_file": null             // Optional HDRI map
  },
  "objects": [],                  // Array of 3D objects (see Object Schema)
  "camera": {},                   // Camera definition (see Camera Schema)
  "lights": [],                   // Array of lights (see Light Schema)
  "materials": []                 // Array of material definitions (see Material Schema)
}
```

---

## Object Schema

Each object in the `objects` array follows this schema:

```json
{
  "name": "string",               // Unique object name (e.g., "maestro_cube")
  "type": "mesh|camera|light",    // Object type
  "mesh": "cube|sphere|plane|cylinder|ico|custom",  // Geometry type
  "location": [0, 0, 0],          // XYZ position (world units)
  "rotation": [0, 0, 0],          // XYZ rotation (degrees)
  "scale": [1, 1, 1],             // XYZ scale factor
  "material": "string",           // Material reference name
  "visible": true,                // Visibility toggle
  "shadeless": false,             // Unlit material (affects lighting)
  
  // For custom meshes only
  "custom_mesh": {
    "type": "file|procedural",
    "source": "path/to/model.blend",  // If type=="file"
    "generator": "string"             // If type=="procedural"
  },
  
  // Modifiers (optional)
  "modifiers": [
    {
      "type": "subdivision|mirror|array|displace",
      "params": {
        "levels": 2,              // For subdivision
        "count": 3,               // For array
        "strength": 0.5           // For displace
      }
    }
  ],
  
  // Animation (keyframes)
  "animation": {
    "keyframes": [
      {
        "frame": 0,               // Frame number (0 = start)
        "location": [0, 0, 0],    // Position at this frame
        "rotation": [0, 0, 0],    // Rotation at this frame
        "scale": [1, 1, 1],       // Scale at this frame
        "easing": "linear"        // Interpolation: linear|ease_in|ease_out|ease_in_out
      },
      {
        "frame": 150,
        "location": [10, 0, 0],
        "rotation": [0, 360, 0],
        "scale": [1, 1, 1],
        "easing": "ease_in_out"
      }
    ],
    "loop": false,                // Loop animation on playback
    "speed": 1.0                  // Playback speed multiplier
  }
}
```

### Built-in Meshes

| Type | Description | Default Scale |
|------|-------------|---|
| `cube` | 2×2×2 unit cube | 1.0 |
| `sphere` | UV sphere (Blender default) | 1.0 |
| `plane` | Flat square plane | 1.0 |
| `cylinder` | Vertical cylinder | r=1, h=2 |
| `ico` | Icosphere (for smooth spheres) | 1.0 |
| `custom` | External .blend or procedural mesh | see custom_mesh |

### Animation Easing Functions

| Type | Behavior |
|------|----------|
| `linear` | Constant speed |
| `ease_in` | Slow start, fast end |
| `ease_out` | Fast start, slow end |
| `ease_in_out` | Slow start, slow end (smooth curve) |

---

## Camera Schema

```json
{
  "name": "Camera",               // Camera object name
  "type": "PERSP",                // PERSP (perspective) or ORTHO (orthographic)
  "focal_length": 50.0,           // 24–85 mm (film camera equivalent)
  "sensor_width": 36.0,           // mm
  "location": [5, 5, 5],          // XYZ position (world units)
  "look_at": [0, 0, 0],           // Point camera aims at
  "depth_of_field": {             // Depth of field (optional)
    "enabled": false,
    "focus_distance": 10.0,
    "f_stop": 2.8                 // Smaller = more blur
  },
  
  // Camera animation (path along curve)
  "animation": {
    "keyframes": [
      {
        "frame": 0,
        "location": [5, 5, 5],
        "look_at": [0, 0, 0],
        "easing": "linear"
      },
      {
        "frame": 150,
        "location": [10, 10, 10],
        "look_at": [2, 2, 2],
        "easing": "ease_in_out"
      }
    ]
  }
}
```

### Camera Types

| Type | Use Case |
|------|----------|
| `PERSP` | Realistic, 3D cinema perspective |
| `ORTHO` | Technical drawings, architectural views |

---

## Light Schema

```json
{
  "name": "Key Light",            // Light name
  "type": "sun|point|spot|area",  // Light type
  "location": [5, 10, 5],         // XYZ position (world units)
  "energy": 2.0,                  // Light intensity (watts/lux)
  "color": [1, 1, 1],             // RGB color (0-1)
  "shadow": {                     // Shadow settings
    "enabled": true,
    "type": "HARD|SOFT",          // Hard or soft shadows
    "softness": 2.0               // Softness radius
  },
  
  // Light-specific properties
  "sun": {                        // For type=="sun"
    "angle": 0.5                  // Angular diameter (degrees)
  },
  "point": {                      // For type=="point"
    "radius": 0.1
  },
  "spot": {                       // For type=="spot"
    "size": 45.0,                 // Cone angle (degrees)
    "blend": 0.15                 // Softness
  },
  "area": {                       // For type=="area"
    "size_x": 2.0,
    "size_y": 2.0
  },
  
  // Light animation (optional)
  "animation": {
    "keyframes": [
      {
        "frame": 0,
        "location": [5, 10, 5],
        "energy": 1.5,
        "easing": "linear"
      },
      {
        "frame": 150,
        "location": [10, 15, 5],
        "energy": 3.0,
        "easing": "ease_out"
      }
    ]
  }
}
```

### Light Types

| Type | Characteristics | Best For |
|------|---|---|
| `sun` | Infinite distance, parallel rays | Key/fill lighting |
| `point` | Omnidirectional from a point | Spot lights, lanterns |
| `spot` | Directional cone | Spotlights, stage lighting |
| `area` | Soft shadows, realistic | Softboxes, window light |

---

## Material Schema

Materials define surface appearance (color, reflectivity, roughness, etc.).

```json
{
  "name": "metallic_blue",        // Material name (referenced by objects)
  "type": "STANDARD|EMISSION",    // Material type
  
  // Base color
  "base_color": [0.1, 0.3, 0.8], // RGB (0-1)
  
  // PBR (Physically-Based Rendering) properties
  "metallic": 0.8,                // 0.0 = non-metal, 1.0 = pure metal
  "roughness": 0.2,               // 0.0 = mirror, 1.0 = completely rough
  "specular": 0.5,                // Specular intensity (IOR)
  "ior": 1.45,                    // Index of Refraction (for transparent materials)
  
  // Textures (optional)
  "textures": [
    {
      "type": "color|normal|roughness|metallic|displacement",
      "source": "path/to/texture.png",
      "scale": [1.0, 1.0],        // UV scale
      "rotation": 0                // Rotation (degrees)
    }
  ],
  
  // Emission (for glowing materials)
  "emission": {
    "enabled": false,
    "color": [1, 1, 1],
    "strength": 0.0               // Emission intensity
  },
  
  // Transparency
  "transparency": {
    "enabled": false,
    "alpha": 1.0,                 // 0.0 = fully transparent, 1.0 = opaque
    "blend_mode": "ALPHA"         // ALPHA, ADD, MULTIPLY
  }
}
```

### Material Types

| Type | Use Case |
|------|----------|
| `STANDARD` | Default Principled BSDF (PBR) |
| `EMISSION` | Light-emitting surface |

### Texture Types

| Type | Purpose |
|------|---------|
| `color` | Base color/albedo |
| `normal` | Surface detail (bump mapping) |
| `roughness` | Per-texel roughness override |
| `metallic` | Per-texel metallic override |
| `displacement` | Geometric deformation |

---

## Complete Example

Here's a complete scene definition for a learning loop 3D animation:

```json
{
  "scene_id": "learning_loop_3d_v1",
  "version": "1.0",
  "title": "Learning Loop 3D Visualization",
  "description": "Interactive 3D representation of the ADR-0314 learning loop",
  "duration": 30.0,
  "framerate": 30,
  "resolution": {
    "width": 1920,
    "height": 1080
  },
  "render_settings": {
    "engine": "CYCLES",
    "samples": 128,
    "use_gpu": true,
    "denoiser": "OPENIMAGEDENOISE"
  },
  "world": {
    "background_color": [0.05, 0.05, 0.1],
    "hdri_file": null
  },
  
  "materials": [
    {
      "name": "maestro_blue",
      "type": "STANDARD",
      "base_color": [0.1, 0.3, 0.8],
      "metallic": 0.7,
      "roughness": 0.1
    },
    {
      "name": "grid_gray",
      "type": "STANDARD",
      "base_color": [0.8, 0.8, 0.8],
      "metallic": 0.0,
      "roughness": 0.5
    }
  ],
  
  "objects": [
    {
      "name": "maestro_cube",
      "type": "mesh",
      "mesh": "cube",
      "location": [0, 0, 0],
      "rotation": [0, 0, 0],
      "scale": [1, 1, 1],
      "material": "maestro_blue",
      "animation": {
        "keyframes": [
          {
            "frame": 0,
            "location": [0, 0, 0],
            "rotation": [0, 0, 0],
            "scale": [1, 1, 1],
            "easing": "linear"
          },
          {
            "frame": 300,
            "location": [0, 0, 0],
            "rotation": [0, 360, 45],
            "scale": [1, 1, 1],
            "easing": "ease_in_out"
          }
        ]
      }
    },
    {
      "name": "ground_plane",
      "type": "mesh",
      "mesh": "plane",
      "location": [0, -2, 0],
      "rotation": [0, 0, 0],
      "scale": [10, 10, 1],
      "material": "grid_gray",
      "visible": true
    }
  ],
  
  "lights": [
    {
      "name": "key_light",
      "type": "area",
      "location": [5, 10, 5],
      "energy": 2.0,
      "color": [1, 1, 1],
      "shadow": {
        "enabled": true,
        "type": "SOFT"
      },
      "area": {
        "size_x": 2.0,
        "size_y": 2.0
      }
    },
    {
      "name": "fill_light",
      "type": "point",
      "location": [-5, 5, 5],
      "energy": 0.8,
      "color": [0.8, 0.9, 1.0],
      "shadow": {
        "enabled": false
      }
    }
  ],
  
  "camera": {
    "name": "Camera",
    "type": "PERSP",
    "focal_length": 50,
    "location": [8, 6, 8],
    "look_at": [0, 0, 0],
    "animation": {
      "keyframes": [
        {
          "frame": 0,
          "location": [8, 6, 8],
          "look_at": [0, 0, 0],
          "easing": "linear"
        },
        {
          "frame": 300,
          "location": [10, 8, 10],
          "look_at": [0, 1, 0],
          "easing": "ease_in_out"
        }
      ]
    }
  }
}
```

---

## Implementation Notes

### For Scene Builder (Phase 2)

1. **Parse JSON Schema**
   - Validate against this schema
   - Convert frame numbers to Blender timeline
   - Calculate world duration in seconds

2. **Create .blend File Programmatically**
   ```python
   import bpy
   
   scene = bpy.data.scenes.new("RenderScene")
   
   # Add objects, materials, lights, camera
   # Wire animations to keyframes
   # Set render settings
   
   bpy.ops.wm.save_as_mainfile(filepath="path/to/output.blend")
   ```

3. **Keyframe Mapping**
   - JSON frame numbers are **relative to scene start** (0 = first frame)
   - Convert to Blender timeline frame: `blender_frame = json_frame`
   - Playback speed: `fps = 30` (or 60)
   - Duration: `total_frames = duration_seconds × fps`

4. **Material Assignment**
   - Materials defined in schema are referenced by name
   - Scene Builder creates materials before objects
   - Objects reference materials by name

### For Quality Metrics (Phase 2)

Estimate render time based on scene complexity:

```python
def estimate_render_time(scene_json):
    samples = scene_json["render_settings"]["samples"]
    object_count = len(scene_json["objects"])
    light_count = len(scene_json["lights"])
    
    # Rough formula (tune after first renders)
    base_time = 5  # seconds for minimal scene
    per_object = 0.1
    per_light = 0.2
    per_sample = 0.01
    
    estimated = base_time + (object_count * per_object) + \
                (light_count * per_light) + (samples * per_sample)
    
    return estimated
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-09-24 | Initial specification (Phase 2) |

---

## Next Steps

1. **Implement Scene Builder** to generate .blend files from this schema
2. **Write validation** to check JSON against schema
3. **Test with example scene** (use the complete example above)
4. **Document Blender Python API** integration points

