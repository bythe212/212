// Sonify dashboard composite.
// input 0 = photo, input 1 = overlay (Script TOP, graphs + text).
// Fits the photo into the image area (aspect kept), draws the scan line and
// dims the part not yet scanned, then lays the overlay on top.
uniform float uScan;      // scan position 0..1
uniform vec4 uImgArea;    // image area (x, y, w, h) in pixels, origin bottom-left
uniform vec4 uLine;       // scan line rgb + glow amount
uniform float uDim;       // brightness of the not-yet-scanned area (1 = unchanged)

out vec4 fragColor;

void main()
{
    vec2 res = uTDOutputInfo.res.zw;
    vec2 px = vUV.st * res;
    vec3 col = vec3(0.035, 0.040, 0.055);

    vec2 imgRes = max(uTD2DInfos[0].res.zw, vec2(1.0));
    float s = min(uImgArea.z / imgRes.x, uImgArea.w / imgRes.y);
    vec2 size = imgRes * s;
    vec2 org = uImgArea.xy + (uImgArea.zw - size) * 0.5;
    vec2 iuv = (px - org) / size;

    if (iuv.x >= 0.0 && iuv.x <= 1.0 && iuv.y >= 0.0 && iuv.y <= 1.0) {
        vec3 c = texture(sTD2DInputs[0], iuv).rgb;
        float played = step(iuv.x, uScan);
        c *= mix(uDim, 1.0, played);
        float d = abs(iuv.x - uScan) * size.x;          // distance to the line in px
        c += uLine.rgb * (clamp(1.0 - d / 1.5, 0.0, 1.0) + uLine.a * exp(-d * 0.06));
        col = c;
    }

    vec4 ov = texture(sTD2DInputs[1], vUV.st);
    col = mix(col, ov.rgb, ov.a);
    fragColor = TDOutputSwizzle(vec4(col, 1.0));
}
