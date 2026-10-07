/* Photoshop 2020 / ExtendScript ES3. Load once, then RetouchRuntime.run(plan).
   No arbitrary string execution; default edits occur on an owned working copy. */
var RetouchRuntime = (function () {
    var VERSION = "1.0.6", MARKER = "__RET_RUNTIME_WORK__";
    function c(s) { return charIDToTypeID(s); }
    function s(v) { return stringIDToTypeID(v); }
    function fail(m) { throw new Error(m); }
    function num(v, lo, hi, label) { if (typeof v !== "number" || !isFinite(v) || v < lo || v > hi) fail("Invalid " + label); return v; }
    function quote(v) { return '"' + String(v).replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\r/g, "\\r").replace(/\n/g, "\\n").replace(/\t/g, "\\t").replace(/[\x00-\x1f]/g, function (x) { return "\\u" + ("0000" + x.charCodeAt(0).toString(16)).slice(-4); }) + '"'; }
    function json(v) {
        var a = [], k, i; if (v === null || v === undefined) return "null";
        if (typeof v === "string") return quote(v); if (typeof v === "number") return isFinite(v) ? String(v) : "null";
        if (typeof v === "boolean") return v ? "true" : "false";
        if (v instanceof Array) { for (i = 0; i < v.length; i++) a.push(json(v[i])); return "[" + a.join(",") + "]"; }
        for (k in v) if (v.hasOwnProperty(k)) a.push(quote(k) + ":" + json(v[k])); return "{" + a.join(",") + "}";
    }
    function iso() { var d = new Date(); function p(n) { return n < 10 ? "0" + n : String(n); } return d.getUTCFullYear() + "-" + p(d.getUTCMonth() + 1) + "-" + p(d.getUTCDate()) + "T" + p(d.getUTCHours()) + ":" + p(d.getUTCMinutes()) + ":" + p(d.getUTCSeconds()) + "Z"; }
    function write(f, value) { f.encoding = "UTF8"; if (!f.open("w")) fail("Cannot write " + f.fsName); try { f.write(json(value)); } finally { f.close(); } }
    function path(p) {
        if (typeof p !== "string") fail("Absolute path without '..' required");
        var normalized = p.split("\\").join("/"), drive = normalized.charAt(0).toUpperCase(), parts = normalized.split("/"), i;
        if (normalized.charAt(0) !== "/" && !(drive >= "A" && drive <= "Z" && normalized.charAt(1) === ":" && normalized.charAt(2) === "/")) fail("Absolute path without '..' required");
        for (i = 0; i < parts.length; i++) if (parts[i] === "..") fail("Absolute path without '..' required");
        normalized = new Folder(p).fsName.split("\\").join("/"); if (normalized.charAt(normalized.length - 1) === "/") normalized = normalized.substring(0, normalized.length - 1); return normalized.toLowerCase();
    }
    function fileName(v, ext) { if (typeof v !== "string" || !/^[A-Za-z0-9][A-Za-z0-9_.-]*$/.test(v) || v.indexOf("..") >= 0 || v.toLowerCase().slice(-ext.length) !== ext) fail("Invalid output filename: " + v); return v; }
    function docByName(name) { var found = null, i; for (i = 0; i < app.documents.length; i++) if (app.documents[i].name === name) { if (found) fail("Ambiguous document name"); found = app.documents[i]; } if (!found) fail("Document not open: " + name); return found; }
    function layers(d, ref) { var hits = []; function walk(x) { var i, l; for (i = 0; i < x.layers.length; i++) { l = x.layers[i]; if ((ref.id !== undefined && l.id === ref.id) || (ref.id === undefined && l.name === ref.name)) hits.push(l); if (l.typename === "LayerSet") walk(l); } } walk(d); return hits; }
    function target(d, ref) { if (!ref || (ref.id === undefined && typeof ref.name !== "string")) fail("Layer selector needs id or unique name"); var a = layers(d, ref); if (a.length !== 1) fail("Layer selector must match exactly once"); return a[0]; }
    function unique(d, name) { if (typeof name !== "string" || !name || name === MARKER || layers(d, { name: name }).length) fail("New layer name must be unique: " + name); }
    function info(d) { return { name: d.name, width: d.width.as("px"), height: d.height.as("px"), bits: String(d.bitsPerChannel), mode: String(d.mode), profile: d.colorProfileName }; }
    function invariant(d, before) { var a = info(d); if (a.width !== before.width || a.height !== before.height || a.bits !== before.bits || a.profile !== before.profile || a.mode !== before.mode) fail("Working document dimensions/depth/profile changed unexpectedly"); }
    function rgb(d) { d.activeChannels = [d.channels[0], d.channels[1], d.channels[2]]; }
    function rect(d, r) { if (!(r instanceof Array) || r.length !== 4) fail("ROI needs [left,top,right,bottom]"); var w = d.width.as("px"), h = d.height.as("px"); num(r[0], 0, w, "ROI left"); num(r[1], 0, h, "ROI top"); num(r[2], 0, w, "ROI right"); num(r[3], 0, h, "ROI bottom"); if (r[0] >= r[2] || r[1] >= r[3]) fail("Empty ROI"); return r; }
    function select(d, r, feather) { d.selection.deselect(); rgb(d); if (!r) { if (feather) fail("Feather requires ROI"); return; } rect(d, r); num(feather || 0, 0, Math.min(r[2] - r[0], r[3] - r[1]) / 2, "feather"); d.selection.select([[r[0], r[1]], [r[2], r[1]], [r[2], r[3]], [r[0], r[3]]], SelectionType.REPLACE, feather || 0, true); }
    function hasMask(l) { var r = new ActionReference(); r.putIdentifier(c("Lyr "), l.id); return executeActionGet(r).getBoolean(s("hasUserMask")); }
    function mask(d, l, kind, r, feather) {
        if (hasMask(l)) fail("Target already has a mask; use a new layer/group");
        select(d, kind === "roi" ? r : [0, 0, d.width.as("px"), d.height.as("px")], kind === "roi" ? feather || 0 : 0);
        // Component-channel activation can change the current target on a group.
        // Select the precise layer only AFTER resetting channels/selection.
        var layerSelect = new ActionDescriptor(), layerRef = new ActionReference(); layerRef.putIdentifier(c("Lyr "), l.id); layerSelect.putReference(c("null"), layerRef); layerSelect.putBoolean(c("MkVs"), false); executeAction(c("slct"), layerSelect, DialogModes.NO);
        var z = new ActionDescriptor(), at = new ActionReference(); z.putClass(c("Nw  "), c("Chnl")); at.putEnumerated(c("Chnl"), c("Chnl"), c("Msk ")); z.putReference(c("At  "), at); z.putEnumerated(c("Usng"), c("UsrM"), c("RvlS"));
        try { executeAction(c("Mk  "), z, DialogModes.NO); } catch (e) { fail("Mask creation failed for " + l.name + " (target id " + l.id + ", active " + d.activeLayer.name + "/" + d.activeLayer.id + "): " + e.message); }
        if (kind === "black") {
            var channelSelect = new ActionDescriptor(), channelRef = new ActionReference(); channelRef.putEnumerated(c("Chnl"), c("Chnl"), c("Msk ")); channelSelect.putReference(c("null"), channelRef); executeAction(c("slct"), channelSelect, DialogModes.NO);
            var black = new SolidColor(); black.rgb.red = black.rgb.green = black.rgb.blue = 0; d.selection.selectAll(); d.selection.fill(black);
        }
        d.selection.deselect(); rgb(d);
    }
    function putParent(d, l, ref) { if (!ref) { if (l.parent.typename !== "Document") l.move(d.layers[0], ElementPlacement.PLACEBEFORE); return; } var p = target(d, ref); if (p.typename !== "LayerSet") fail("Parent must be a group"); if (l.parent.typename !== "LayerSet" || l.parent.id !== p.id) l.move(p, ElementPlacement.INSIDE); }
    function style(l, op, mode) { l.opacity = num(op.opacity === undefined ? 100 : op.opacity, 0, 100, "opacity"); l.blendMode = mode; }
    function curve(d, op) {
        unique(d, op.name); var p = op.points, i, last = -1, chan = op.channel || "Cmps"; if (!(p instanceof Array) || p.length < 2 || p.length > 32 || (chan !== "Cmps" && chan !== "Rd  " && chan !== "Grn " && chan !== "Bl  ")) fail("Invalid curve channel/points");
        for (i = 0; i < p.length; i++) { if (!(p[i] instanceof Array) || p[i].length !== 2) fail("Curve point needs x,y"); num(p[i][0], 0, 255, "curve x"); num(p[i][1], 0, 255, "curve y"); if (p[i][0] <= last) fail("Curve x must increase"); last = p[i][0]; }
        select(d, op.roi, op.feather); var settings = new ActionDescriptor(), list = new ActionList(), crv = new ActionDescriptor(), ref = new ActionReference(), points = new ActionList(); ref.putEnumerated(c("Chnl"), c("Chnl"), c(chan)); crv.putReference(c("Chnl"), ref);
        for (i = 0; i < p.length; i++) { var pt = new ActionDescriptor(); pt.putDouble(c("Hrzn"), p[i][0]); pt.putDouble(c("Vrtc"), p[i][1]); points.putObject(c("Pnt "), pt); } crv.putList(c("Crv "), points); list.putObject(c("CrvA"), crv); settings.putList(c("Adjs"), list);
        var z = new ActionDescriptor(), to = new ActionReference(), use = new ActionDescriptor(); to.putClass(c("AdjL")); z.putReference(c("null"), to); use.putString(c("Nm  "), op.name); use.putObject(c("Type"), c("Crvs"), settings); z.putObject(c("Usng"), c("AdjL"), use); executeAction(c("Mk  "), z, DialogModes.NO);
        var l = d.activeLayer; putParent(d, l, op.parent); style(l, op, op.blend === "normal" ? BlendMode.NORMAL : BlendMode.LUMINOSITY); d.selection.deselect(); rgb(d); return l;
    }
    function color(d, op) {
        unique(d, op.name); var values = op.rgb, i; if (!(values instanceof Array) || values.length !== 3) fail("Color needs RGB triple"); for (i = 0; i < 3; i++) num(values[i], 0, 255, "RGB"); select(d, op.roi, op.feather);
        var z = new ActionDescriptor(), ref = new ActionReference(), use = new ActionDescriptor(), fill = new ActionDescriptor(), co = new ActionDescriptor(); ref.putClass(s("contentLayer")); z.putReference(c("null"), ref); use.putString(c("Nm  "), op.name); co.putDouble(c("Rd  "), values[0]); co.putDouble(c("Grn "), values[1]); co.putDouble(c("Bl  "), values[2]); fill.putObject(c("Clr "), c("RGBC"), co); use.putObject(c("Type"), s("solidColorLayer"), fill); z.putObject(c("Usng"), s("contentLayer"), use); executeAction(c("Mk  "), z, DialogModes.NO);
        var l = d.activeLayer; putParent(d, l, op.parent); style(l, op, BlendMode.COLORBLEND); if (op.clipTo) { var donor = target(d, op.clipTo); l.move(donor, ElementPlacement.PLACEBEFORE); l.grouped = true; } d.selection.deselect(); rgb(d); return l;
    }
    function importMask(d, op, ctx) {
        var l = target(d, op.target), f = new File(op.path), i, md = null, ch = null; if (!f.exists) fail("Mask file not found"); if (hasMask(l)) fail("Mask import requires target without mask");
        for (i = 0; i < app.documents.length; i++) { try { if (app.documents[i].fullName.fsName === f.fsName) fail("Mask file is already open; close it before import"); } catch (e) { if (String(e.message).indexOf("already open") >= 0) throw e; } }
        try { md = app.open(f); ctx.temps.push(md); if (md.mode !== DocumentMode.GRAYSCALE || md.width.as("px") !== d.width.as("px") || md.height.as("px") !== d.height.as("px")) fail("Mask must be grayscale and match working canvas exactly"); md.bitsPerChannel = d.bitsPerChannel; ch = md.channels[0].duplicate(d); app.activeDocument = d; d.activeLayer = l; rgb(d); d.selection.load(ch, SelectionType.REPLACE);
            var z = new ActionDescriptor(), ref = new ActionReference(); z.putClass(c("Nw  "), c("Chnl")); ref.putEnumerated(c("Chnl"), c("Chnl"), c("Msk ")); z.putReference(c("At  "), ref); z.putEnumerated(c("Usng"), c("UsrM"), c("RvlS")); executeAction(c("Mk  "), z, DialogModes.NO);
        } finally { app.activeDocument = d; if (ch) try { ch.remove(); } catch (ignore) {} d.selection.deselect(); rgb(d); if (md) { md.close(SaveOptions.DONOTSAVECHANGES); ctx.temps.pop(); } } return l;
    }
    function output(ctx, name, ext) { var f = new File(ctx.dir.fsName + "/" + fileName(name, ext)); if (f.exists) fail("Refusing overwrite: " + f.fsName); return f; }
    function asset(f, d, kind, crop) { return { path: f.fsName, bytes: f.length, kind: kind, width: d.width.as("px"), height: d.height.as("px"), bits: String(d.bitsPerChannel), profile: d.colorProfileName, crop: crop || null }; }
    function closeTemp(ctx, d) { d.close(SaveOptions.DONOTSAVECHANGES); ctx.temps.pop(); }
    function preview(d, op, ctx) {
        var f = output(ctx, op.file, ".png"), t = d.duplicate("RT_preview_" + ctx.id, true); ctx.temps.push(t); app.activeDocument = t;
        if (op.roi) { rect(d, op.roi); t.crop([UnitValue(op.roi[0], "px"), UnitValue(op.roi[1], "px"), UnitValue(op.roi[2], "px"), UnitValue(op.roi[3], "px")]); }
        t.convertProfile("sRGB IEC61966-2.1", Intent.RELATIVECOLORIMETRIC, true, false); t.bitsPerChannel = BitsPerChannelType.EIGHT;
        var max = num(op.maxDimension === undefined ? 1200 : op.maxDimension, 64, 4096, "preview dimension"), w = t.width.as("px"), h = t.height.as("px"); if (Math.max(w, h) > max) t.resizeImage(UnitValue(Math.round(w * max / Math.max(w, h)), "px"), UnitValue(Math.round(h * max / Math.max(w, h)), "px"), undefined, ResampleMethod.BICUBIC);
        var opts = new PNGSaveOptions(); opts.interlaced = false; t.saveAs(f, opts, true, Extension.LOWERCASE); ctx.manifest.assets.push(asset(f, t, "sRGB8_preview", op.roi)); closeTemp(ctx, t); app.activeDocument = d;
    }
    function exports(d, op, ctx) {
        var variants = op.variants || [{ name: "full", psd: op.psd, png: op.png }], i, t, pngDoc, v, f, opts; if (!(variants instanceof Array) || !variants.length) fail("Export needs variants");
        for (i = 0; i < variants.length; i++) { v = variants[i]; if (!v.psd && !v.png) fail("Variant needs psd and/or png"); if (v.crop) { rect(d, v.crop); for (var q = 0; q < 4; q++) if (v.crop[q] !== Math.round(v.crop[q])) fail("Crop coordinates must be integer pixels"); } t = d;
            if (v.crop) { t = d.duplicate("RT_crop_" + ctx.id + "_" + i, false); ctx.temps.push(t); app.activeDocument = t; t.selection.deselect(); rgb(t); t.crop([UnitValue(v.crop[0], "px"), UnitValue(v.crop[1], "px"), UnitValue(v.crop[2], "px"), UnitValue(v.crop[3], "px")]); }
            if (v.psd) { f = output(ctx, v.psd, ".psd"); opts = new PhotoshopSaveOptions(); opts.layers = true; opts.alphaChannels = true; opts.embedColorProfile = true; t.saveAs(f, opts, true, Extension.LOWERCASE); ctx.manifest.assets.push(asset(f, t, "layered_native_psd", v.crop)); }
            if (v.png) { f = output(ctx, v.png, ".png"); pngDoc = t.duplicate("RT_png_" + ctx.id + "_" + i, true); ctx.temps.push(pngDoc); app.activeDocument = pngDoc; opts = new PNGSaveOptions(); opts.interlaced = false; pngDoc.saveAs(f, opts, true, Extension.LOWERCASE); ctx.manifest.assets.push(asset(f, pngDoc, "native_png", v.crop)); closeTemp(ctx, pngDoc); }
            if (v.crop) closeTemp(ctx, t); app.activeDocument = d; write(ctx.file, ctx.manifest);
        }
    }
    function perform(d, op, ctx) {
        var l, p; rgb(d); d.selection.deselect();
        if (op.type === "group") { unique(d, op.name); l = d.layerSets.add(); l.name = op.name; putParent(d, l, op.parent); if (op.mask) { if (op.mask !== "black" && op.mask !== "white" && op.mask !== "roi") fail("Invalid mask kind"); mask(d, l, op.mask, op.roi, op.feather); } }
        else if (op.type === "curve") l = curve(d, op);
        else if (op.type === "color") l = color(d, op);
        else if (op.type === "mask") { l = target(d, op.target); if (op.kind !== "black" && op.kind !== "white" && op.kind !== "roi") fail("Invalid mask kind"); mask(d, l, op.kind, op.roi, op.feather); }
        else if (op.type === "importMask") l = importMask(d, op, ctx);
        else if (op.type === "checks") { unique(d, op.name); unique(d, op.name + "_gray"); unique(d, op.name + "_contrast"); l = d.layerSets.add(); l.name = op.name; color(d, { name: op.name + "_gray", rgb: [255, 255, 255], parent: { id: l.id } }); curve(d, { name: op.name + "_contrast", parent: { id: l.id }, points: [[0, 0], [64, 35], [128, 128], [192, 220], [255, 255]] }); l.visible = false; }
        else if (op.type === "preview") preview(d, op, ctx);
        else if (op.type === "checkPreview") { l = target(d, op.target); if (l.typename !== "LayerSet") fail("Check target must be a group"); var visible = l.visible; try { l.visible = true; preview(d, op, ctx); } finally { l.visible = visible; } }
        else if (op.type === "export") exports(d, op, ctx);
        else fail("Unsupported operation: " + op.type);
        d.selection.deselect(); rgb(d); return l ? { id: l.id, name: l.name } : null;
    }
    function run(plan) {
        if (!plan || !/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(plan.jobId || "")) fail("Safe jobId required"); if (plan.mode !== "probe" && plan.mode !== "edit") fail("mode must be probe or edit");
        path(plan.outputDir); var source = docByName(plan.documentName), before = info(source), original = app.activeDocument, oldDialogs = app.displayDialogs, oldUnits = app.preferences.rulerUnits, root = new Folder(plan.outputDir), allowed = false, i, started = new Date().getTime(), d = null, copied = false, history = null, error = null;
        if (!(plan.allowlistedOutputDirs instanceof Array)) fail("allowlistedOutputDirs required"); for (i = 0; i < plan.allowlistedOutputDirs.length; i++) if (path(root.fsName) === path(plan.allowlistedOutputDirs[i])) allowed = true; if (!allowed || root.alias) fail("outputDir is not an allowlisted directory");
        var dir = new Folder(root.fsName + "/" + plan.jobId); if (dir.exists) fail("Job directory exists: inspect manifest; do not resubmit same job"); if (!root.exists && !root.create()) fail("Cannot create outputDir"); if (!dir.create()) fail("Cannot create job directory");
        var ctx = { id: plan.jobId, dir: dir, file: new File(dir.fsName + "/manifest.json"), temps: [], manifest: { version: VERSION, jobId: plan.jobId, status: "started", startedAt: iso(), source: before, workingDocument: null, stages: [], assets: [] } }; write(ctx.file, ctx.manifest);
        try {
            app.displayDialogs = DialogModes.NO; app.preferences.rulerUnits = Units.PIXELS;
            if (plan.mode === "probe") ctx.manifest.probe = { photoshopVersion: app.version, documentCount: app.documents.length, runtime: VERSION };
            else {
                if (source.mode !== DocumentMode.RGB || (source.bitsPerChannel !== BitsPerChannelType.EIGHT && source.bitsPerChannel !== BitsPerChannelType.SIXTEEN)) fail("Editing supports RGB8/RGB16 only");
                var setupStart = new Date().getTime(); app.activeDocument = source;
                if (plan.reuseWorkingDocument === true) { if (layers(source, { name: MARKER }).length !== 1) fail("Continuation requires runtime-owned working document marker"); if (plan.protectedOriginalNames) for (i = 0; i < plan.protectedOriginalNames.length; i++) if (source.name === plan.protectedOriginalNames[i]) fail("Protected original document"); d = source; history = d.activeHistoryState; }
                else { var workName = plan.workingDocumentName || "RT_" + plan.jobId; for (i = 0; i < app.documents.length; i++) if (app.documents[i].name === workName) fail("Working name is already open"); d = source.duplicate(workName, false); copied = true; app.activeDocument = d; var markers = layers(d, { name: MARKER }); if (markers.length > 1) fail("Ambiguous working document ownership markers"); var marker = markers.length === 1 ? markers[0] : d.layerSets.add(); marker.name = MARKER; marker.visible = false; }
                ctx.manifest.setupElapsedMs = new Date().getTime() - setupStart;
                app.activeDocument = d; rgb(d); d.selection.deselect(); ctx.manifest.workingDocument = d.name; ctx.manifest.status = "running"; write(ctx.file, ctx.manifest);
                var ops = plan.operations || []; if (!(ops instanceof Array)) fail("operations must be array");
                for (i = 0; i < ops.length; i++) { var st = { index: i, type: ops[i].type, name: ops[i].name || null, status: "running", startedAt: iso() }, tick = new Date().getTime(); ctx.manifest.stages.push(st); write(ctx.file, ctx.manifest); st.layer = perform(d, ops[i], ctx); invariant(d, before); st.elapsedMs = new Date().getTime() - tick; st.status = "complete"; write(ctx.file, ctx.manifest); }
                ctx.manifest.working = info(d); if (copied) invariant(source, before);
            }
        } catch (e) { error = e; ctx.manifest.error = { message: String(e.message), line: e.line || null }; if (ctx.manifest.stages.length) { var lastStage = ctx.manifest.stages[ctx.manifest.stages.length - 1]; if (lastStage.status === "running") lastStage.status = "failed"; } }
        finally {
            while (ctx.temps.length) { try { ctx.temps.pop().close(SaveOptions.DONOTSAVECHANGES); } catch (closeError) { if (!error) error = closeError; } }
            if (d) { try { app.activeDocument = d; d.selection.deselect(); rgb(d); if (error && !copied && history) d.activeHistoryState = history; if (copied && (error || plan.keepWorkingDocument === false)) d.close(SaveOptions.DONOTSAVECHANGES); } catch (cleanupError) { if (!error) error = cleanupError; } }
            try { app.displayDialogs = oldDialogs; app.preferences.rulerUnits = oldUnits; app.activeDocument = original; } catch (restoreError) { if (!error) error = restoreError; }
            ctx.manifest.status = error ? "failed" : "complete"; ctx.manifest.finishedAt = iso(); ctx.manifest.elapsedMs = new Date().getTime() - started; if (error && !ctx.manifest.error) ctx.manifest.error = { message: String(error.message) }; write(ctx.file, ctx.manifest);
        }
        return ctx.manifest;
    }
    return { version: VERSION, run: run };
}());
