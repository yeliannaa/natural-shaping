<#
.SYNOPSIS
Read-only PNG integrity, native-pixel, allowed-edit and exact-crop verification.
.EXAMPLE
./verify_native_png.ps1 -Png after.png -Before before.png -AllowedRoi @(100,200,300,400) -Report qa.json
.EXAMPLE
./verify_native_png.ps1 -Png crop.png -CropOf full.png -CropRect @(550,100,3250,3475)
.NOTES
Bounds exclude the right/bottom edge. AllowedRoi accepts one or more flattened x1,y1,x2,y2 rectangles.
ExpectedDepth defaults to 16. Use 8 explicitly for previews; that never certifies a native 16-bit master.
Embedded RGB ICC is required by default. AllowMissingIcc explicitly permits absent ICC; sRGB/gAMA/cHRM tags are still inspected and compared. Absent ICC does not mean untagged colour.
RGB and RGBA are supported; comparisons include every actual channel, including alpha when present.
Exit codes: 0 passed, 1 failed checks, 2 invalid input/unsupported format/error. Never overwrites an input.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Png,
    [string]$Before,
    [int[]]$AllowedRoi=@(),
    [string]$CropOf,
    [int[]]$CropRect=@(),
    [string]$Report,
    [ValidateSet(8,16)][int]$ExpectedDepth=16,
    [switch]$AllowMissingIcc
)
$ErrorActionPreference='Stop'
$source=@'
using System;
using System.IO;
using System.IO.Compression;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
public static class RetouchNativePngQA {
    public sealed class Raster { public int Width,Height,Depth,Channels; public byte[] Pixels; public string IccHash,ColorDefinitionHash; public Dictionary<string,object> Metadata; }
    static uint U32(byte[] b,int o) { return ((uint)b[o]<<24)|((uint)b[o+1]<<16)|((uint)b[o+2]<<8)|b[o+3]; }
    static byte[] Bytes(BinaryReader b,int n) { byte[] d=b.ReadBytes(n);if(d.Length!=n)throw new InvalidDataException("Truncated PNG");return d; }
    static string Hash(byte[] d) { using(var h=SHA256.Create())return BitConverter.ToString(h.ComputeHash(d)).Replace("-","").ToLowerInvariant(); }
    static readonly uint[] Table=MakeTable();
    static uint[] MakeTable() { var t=new uint[256];for(uint i=0;i<256;i++){uint c=i;for(int k=0;k<8;k++)c=(c&1)!=0?0xedb88320u^(c>>1):c>>1;t[i]=c;}return t; }
    static uint Crc(byte[] t,byte[] d) { uint c=0xffffffffu;foreach(byte v in t)c=Table[(c^v)&255]^(c>>8);foreach(byte v in d)c=Table[(c^v)&255]^(c>>8);return c^0xffffffffu; }
    static byte[] Inflate(byte[] compressed,int exactBytes) {
        if(compressed.Length<6||(compressed[0]&15)!=8||(compressed[0]>>4)>7||((compressed[0]<<8)|compressed[1])%31!=0||(compressed[1]&32)!=0)throw new InvalidDataException("Invalid or unsupported zlib header");
        int limit=exactBytes>=0?exactBytes:16*1024*1024;byte[] output;
        using(var input=new MemoryStream(compressed,2,compressed.Length-6))using(var z=new DeflateStream(input,CompressionMode.Decompress))using(var raw=new MemoryStream()) {
            byte[] buffer=new byte[65536];int n;while((n=z.Read(buffer,0,buffer.Length))>0){if(raw.Length+n>limit)throw new InvalidDataException("Inflated PNG/ICC exceeds expected size");raw.Write(buffer,0,n);}output=raw.ToArray();
        }
        if(exactBytes>=0&&output.Length!=exactBytes)throw new InvalidDataException("Truncated or oversized decompressed PNG scanlines");
        uint a=1,b=0;foreach(byte v in output){a=(a+v)%65521;b=(b+a)%65521;}if(((b<<16)|a)!=U32(compressed,compressed.Length-4))throw new InvalidDataException("Zlib Adler32 mismatch");return output;
    }
    static int Paeth(int a,int b,int c) { int p=a+b-c,pa=Math.Abs(p-a),pb=Math.Abs(p-b),pc=Math.Abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c; }
    static void ValidateIcc(byte[] icc) {
        if(icc.Length<132||U32(icc,0)!=icc.Length||Encoding.ASCII.GetString(icc,36,4)!="acsp"||Encoding.ASCII.GetString(icc,16,4)!="RGB ")throw new InvalidDataException("Invalid embedded RGB ICC header/length");
        uint count=U32(icc,128);long tableEnd=132L+12L*count;if(tableEnd>icc.Length)throw new InvalidDataException("Truncated ICC tag table");
        for(uint i=0;i<count;i++){int pos=132+(int)i*12;uint offset=U32(icc,pos+4),size=U32(icc,pos+8);if(offset<tableEnd||offset%4!=0||size<8||(long)offset+size>icc.Length)throw new InvalidDataException("ICC tag outside profile bounds");}
    }
    public static Raster Read(string path,int expectedDepth,bool allowMissingIcc) {
        var r=new Raster();r.Metadata=new Dictionary<string,object>();byte[] icc=null;int chunks=0,iccCount=0;bool header=false,idat=false,idatEnded=false,ended=false;string profileName=null,srgbHash=null,gammaHash=null,chromaHash=null;int? srgbIntent=null;uint? gamma=null;uint[] chromaticities=null;
        using(var f=File.OpenRead(path))using(var b=new BinaryReader(f))using(var compressed=new MemoryStream()) {
            if(BitConverter.ToString(Bytes(b,8))!="89-50-4E-47-0D-0A-1A-0A")throw new InvalidDataException("Bad PNG signature");
            while(f.Position<f.Length) {
                uint n=U32(Bytes(b,4),0);byte[] typeBytes=Bytes(b,4);string type=Encoding.ASCII.GetString(typeBytes);
                foreach(byte v in typeBytes)if(!((v>=65&&v<=90)||(v>=97&&v<=122)))throw new InvalidDataException("Invalid PNG chunk type");
                if((typeBytes[2]&32)!=0)throw new InvalidDataException("Invalid PNG reserved chunk bit");
                if(n>Int32.MaxValue||f.Position+(long)n+4>f.Length)throw new InvalidDataException("Truncated PNG chunk: "+type);
                byte[] d=Bytes(b,(int)n);if(Crc(typeBytes,d)!=U32(Bytes(b,4),0))throw new InvalidDataException("PNG CRC mismatch: "+type);
                if(chunks==0&&type!="IHDR")throw new InvalidDataException("IHDR must be first");
                if(type=="IHDR") {
                    if(header||d.Length!=13)throw new InvalidDataException("Invalid/duplicate IHDR");header=true;
                    uint w=U32(d,0),h=U32(d,4);if(w==0||h==0||w>Int32.MaxValue||h>Int32.MaxValue)throw new InvalidDataException("Invalid PNG dimensions");
                    r.Width=(int)w;r.Height=(int)h;r.Depth=d[8];r.Channels=d[9]==2?3:d[9]==6?4:0;
                    if(r.Depth!=expectedDepth||r.Channels==0||d[10]!=0||d[11]!=0||d[12]!=0)throw new InvalidDataException("Expected noninterlaced RGB/RGBA PNG at depth "+expectedDepth+"; actual depth="+r.Depth+", colorType="+d[9]);
                    r.Metadata["colorType"]=d[9];r.Metadata["interlace"]=d[12];r.Metadata["ihdrSha256"]=Hash(d);
                } else if(type=="iCCP") {
                    if(++iccCount!=1||idat)throw new InvalidDataException("Invalid iCCP placement/count");int zero=Array.IndexOf(d,(byte)0);
                    if(zero<1||zero>79||zero+2>=d.Length||d[zero+1]!=0)throw new InvalidDataException("Invalid iCCP");
                    profileName=Encoding.ASCII.GetString(d,0,zero);byte[] z=new byte[d.Length-zero-2];Buffer.BlockCopy(d,zero+2,z,0,z.Length);icc=Inflate(z,-1);
                    ValidateIcc(icc);
                } else if(type=="sRGB") {
                    if(srgbHash!=null||idat||d.Length!=1||d[0]>3)throw new InvalidDataException("Invalid sRGB chunk");srgbHash=Hash(d);srgbIntent=d[0];
                } else if(type=="gAMA") {
                    if(gammaHash!=null||idat||d.Length!=4||U32(d,0)==0)throw new InvalidDataException("Invalid gAMA chunk");gammaHash=Hash(d);gamma=U32(d,0);
                } else if(type=="cHRM") {
                    if(chromaHash!=null||idat||d.Length!=32)throw new InvalidDataException("Invalid cHRM chunk");chromaHash=Hash(d);chromaticities=new uint[8];for(int i=0;i<8;i++)chromaticities[i]=U32(d,i*4);
                } else if(type=="IDAT") {
                    if(idatEnded)throw new InvalidDataException("Nonconsecutive IDAT chunks");idat=true;compressed.Write(d,0,d.Length);
                } else if(type=="IEND") {
                    if(d.Length!=0||!idat)throw new InvalidDataException("Invalid IEND");ended=true;if(f.Position!=f.Length)throw new InvalidDataException("Trailing PNG bytes");
                } else if(type=="PLTE") {
                    if(idat||d.Length==0||d.Length>768||d.Length%3!=0)throw new InvalidDataException("Invalid optional RGB PLTE");
                } else if((typeBytes[0]&32)==0)throw new InvalidDataException("Unsupported critical PNG chunk: "+type);
                if(idat&&type!="IDAT")idatEnded=true;chunks++;if(ended)break;
            }
            if(!header||!idat||!ended)throw new InvalidDataException("Incomplete PNG chunk stream");if(icc!=null&&srgbHash!=null)throw new InvalidDataException("PNG contains mutually exclusive iCCP and sRGB chunks");if(icc==null&&!allowMissingIcc)throw new InvalidDataException("Embedded ICC missing; colour definition="+(srgbHash!=null?"sRGB chunk":gammaHash!=null||chromaHash!=null?"gAMA/cHRM tags":"unspecified")+". Explicit AllowMissingIcc is required to accept absent ICC");
            long bpp=r.Channels*(r.Depth/8),stride=(long)r.Width*bpp,rawSize=(stride+1)*r.Height,pixelSize=stride*r.Height;
            if(rawSize>Int32.MaxValue||pixelSize>Int32.MaxValue)throw new InvalidDataException("PNG too large for bounded native reader");
            byte[] encoded=Inflate(compressed.ToArray(),(int)rawSize);r.Pixels=new byte[(int)pixelSize];
            for(int y=0;y<r.Height;y++) {
                int start=y*(int)stride,read=y*((int)stride+1),filter=encoded[read++];if(filter>4)throw new InvalidDataException("Invalid PNG scanline filter");
                for(int x=0;x<(int)stride;x++){int left=x>=bpp?r.Pixels[start+x-(int)bpp]:0,up=y>0?r.Pixels[start+x-(int)stride]:0,ul=y>0&&x>=bpp?r.Pixels[start+x-(int)stride-(int)bpp]:0,p=filter==0?0:filter==1?left:filter==2?up:filter==3?(left+up)/2:Paeth(left,up,ul);r.Pixels[start+x]=(byte)((encoded[read+x]+p)&255);}
            }
            r.Metadata["fileBytes"]=f.Length;
        }
        r.IccHash=icc==null?null:Hash(icc);r.ColorDefinitionHash=Hash(Encoding.ASCII.GetBytes((r.IccHash??"noICC")+"|"+(srgbHash??"noSRGB")+"|"+(gammaHash??"noGamma")+"|"+(chromaHash??"noChroma")));long nonopaque=0;int minAlpha=r.Depth==16?65535:255;
        if(r.Channels==4)for(int i=0;i<r.Pixels.Length;i+=4*(r.Depth/8)){int p=i+3*(r.Depth/8),alpha=r.Depth==16?(r.Pixels[p]<<8)|r.Pixels[p+1]:r.Pixels[p];if(alpha<(r.Depth==16?65535:255))nonopaque++;minAlpha=Math.Min(minAlpha,alpha);}
        r.Metadata["width"]=r.Width;r.Metadata["height"]=r.Height;r.Metadata["depthBits"]=r.Depth;r.Metadata["channels"]=r.Channels;r.Metadata["completeChunkStream"]=true;r.Metadata["allChunkCrcsValid"]=true;r.Metadata["zlibAdler32Valid"]=true;r.Metadata["chunkCount"]=chunks;r.Metadata["decodedPixelBytes"]=r.Pixels.LongLength;r.Metadata["iccBytes"]=icc==null?0:icc.Length;r.Metadata["iccSha256"]=r.IccHash;r.Metadata["profileName"]=profileName;r.Metadata["embeddedRgbIccValidated"]=icc!=null;r.Metadata["sRgbRenderingIntent"]=srgbIntent;r.Metadata["gammaTimes100000"]=gamma;r.Metadata["chromaticitiesTimes100000"]=chromaticities;r.Metadata["colorDefinition"]=icc!=null?"embedded RGB ICC":srgbHash!=null?"sRGB chunk":gammaHash!=null&&chromaHash!=null?"gAMA + cHRM":gammaHash!=null||chromaHash!=null?"partial gAMA/cHRM tags":"unspecified";r.Metadata["colorDefinitionSha256"]=r.ColorDefinitionHash;r.Metadata["hasAlphaChannel"]=r.Channels==4;r.Metadata["nonopaquePixelCount"]=nonopaque;r.Metadata["minimumAlpha"]=minAlpha;return r;
    }
    static bool Inside(int x,int y,int[] boxes) { for(int i=0;i<boxes.Length;i+=4)if(x>=boxes[i]&&y>=boxes[i+1]&&x<boxes[i+2]&&y<boxes[i+3])return true;return false; }
    public static void ValidateBoxes(int[] boxes,int width,int height) { if(boxes.Length%4!=0)throw new ArgumentException("ROI arrays require flattened x1,y1,x2,y2 groups");for(int i=0;i<boxes.Length;i+=4)if(boxes[i]<0||boxes[i+1]<0||boxes[i+2]<=boxes[i]||boxes[i+3]<=boxes[i+1]||boxes[i+2]>width||boxes[i+3]>height)throw new ArgumentException("ROI outside raster or empty"); }
    public static Dictionary<string,object> Compare(Raster reference,Raster target,int dx,int dy,int[] allowed) {
        if(reference.Depth!=target.Depth||reference.Channels!=target.Channels||dx<0||dy<0||dx+target.Width>reference.Width||dy+target.Height>reference.Height)throw new ArgumentException("Comparison dimensions/channel formats do not match");
        ValidateBoxes(allowed,target.Width,target.Height);int bytesPerSample=target.Depth/8,bpp=target.Channels*bytesPerSample,max=0,minX=target.Width,minY=target.Height,maxX=-1,maxY=-1,outMinX=target.Width,outMinY=target.Height,outMaxX=-1,outMaxY=-1;long changed=0,outside=0,samples=0;var examples=new List<int[]>();
        for(int y=0;y<target.Height;y++)for(int x=0;x<target.Width;x++) {
            int ai=((y+dy)*reference.Width+x+dx)*bpp,bi=(y*target.Width+x)*bpp;bool different=false;
            for(int c=0;c<target.Channels;c++){int j=c*bytesPerSample,av=bytesPerSample==2?(reference.Pixels[ai+j]<<8)|reference.Pixels[ai+j+1]:reference.Pixels[ai+j],bv=bytesPerSample==2?(target.Pixels[bi+j]<<8)|target.Pixels[bi+j+1]:target.Pixels[bi+j],delta=Math.Abs(av-bv);if(delta>0){different=true;samples++;}max=Math.Max(max,delta);}
            if(!different)continue;changed++;minX=Math.Min(minX,x);minY=Math.Min(minY,y);maxX=Math.Max(maxX,x);maxY=Math.Max(maxY,y);
            if(!Inside(x,y,allowed)){outside++;outMinX=Math.Min(outMinX,x);outMinY=Math.Min(outMinY,y);outMaxX=Math.Max(outMaxX,x);outMaxY=Math.Max(outMaxY,y);if(examples.Count<12)examples.Add(new int[]{x,y});}
        }
        return new Dictionary<string,object>{{"comparedPixels",(long)target.Width*target.Height},{"depthBits",target.Depth},{"comparedChannels",target.Channels},{"alphaIncluded",target.Channels==4},{"referenceOffset",new int[]{dx,dy}},{"allowedRoisExclusiveFlattened",allowed},{"changedPixels",changed},{"changedChannelSamples",samples},{"maximumChannelDifference",max},{"changedBoundsExclusive",changed==0?null:(object)new int[]{minX,minY,maxX+1,maxY+1}},{"changedPixelsOutsideAllowedRois",outside},{"changedBoundsOutsideAllowedRoisExclusive",outside==0?null:(object)new int[]{outMinX,outMinY,outMaxX+1,outMaxY+1}},{"outsideMismatchExamples",examples},{"allPixelsIdentical",changed==0},{"outsideAllowedRoisIdentical",outside==0},{"iccProfilesEmbeddedInBoth",reference.IccHash!=null&&target.IccHash!=null},{"iccByteIdentical",reference.IccHash!=null&&reference.IccHash==target.IccHash},{"iccPresenceAndBytesMatch",reference.IccHash==target.IccHash},{"colorDefinitionPreserved",reference.ColorDefinitionHash==target.ColorDefinitionHash}};
    }
}
'@
$result=[ordered]@{status='error';createdAtUtc=[DateTime]::UtcNow.ToString('o');expectedDepth=$ExpectedDepth;kind=if($ExpectedDepth -eq 16){'native 16-bit PNG verification'}else{'8-bit preview verification; does not certify a 16-bit master'};allowMissingIcc=[bool]$AllowMissingIcc;visualQualityVerified=$false;colorDefinitionScope='PNG iCCP/sRGB/gAMA/cHRM chunks; an XMP profile name is descriptive metadata and is not treated as embedded ICC bytes';boundsConvention='left/top inclusive, right/bottom exclusive';metadata=[ordered]@{};checks=[ordered]@{}}
$exitCode=2;$reportSafe=$true;$reportPath=$null
try {
    $paths=[ordered]@{png=[IO.Path]::GetFullPath($Png)}
    if($Before){$paths.before=[IO.Path]::GetFullPath($Before)}
    if($CropOf){$paths.cropOf=[IO.Path]::GetFullPath($CropOf)}
    if($Report){$reportPath=[IO.Path]::GetFullPath($Report);foreach($path in $paths.Values){if([StringComparer]::OrdinalIgnoreCase.Equals($reportPath,$path)){$reportSafe=$false;throw 'Report path equals an input path; input will not be overwritten'}}}
    if($AllowedRoi.Length -gt 0 -and -not $Before){throw 'AllowedRoi requires Before'}
    if(($CropOf -and $CropRect.Length -ne 4) -or (-not $CropOf -and $CropRect.Length -ne 0)){throw 'CropOf requires exactly four CropRect coordinates, and CropRect requires CropOf'}
    if(-not ('RetouchNativePngQA' -as [type])){Add-Type -TypeDefinition $source}
    $hashesBefore=[ordered]@{};$rasters=[ordered]@{}
    foreach($key in $paths.Keys){if(-not [IO.File]::Exists($paths[$key])){throw "Input PNG missing: $($paths[$key])"};$hashesBefore[$key]=(Get-FileHash -LiteralPath $paths[$key] -Algorithm SHA256).Hash.ToLowerInvariant();$rasters[$key]=[RetouchNativePngQA]::Read($paths[$key],$ExpectedDepth,[bool]$AllowMissingIcc);$result.metadata[$key]=$rasters[$key].Metadata}
    $passed=$true
    if($Before){if($rasters.before.Width -ne $rasters.png.Width -or $rasters.before.Height -ne $rasters.png.Height){throw 'Before and Png dimensions differ'};$check=[RetouchNativePngQA]::Compare($rasters.before,$rasters.png,0,0,$AllowedRoi);$result.checks.before=$check;$passed=$passed -and $check.outsideAllowedRoisIdentical -and $check.iccPresenceAndBytesMatch -and $check.colorDefinitionPreserved}
    if($CropOf){[RetouchNativePngQA]::ValidateBoxes($CropRect,$rasters.cropOf.Width,$rasters.cropOf.Height);if($rasters.png.Width -ne $CropRect[2]-$CropRect[0] -or $rasters.png.Height -ne $CropRect[3]-$CropRect[1]){throw 'Png dimensions do not equal CropRect dimensions'};$check=[RetouchNativePngQA]::Compare($rasters.cropOf,$rasters.png,$CropRect[0],$CropRect[1],[int[]]@());$check['cropRectExclusive']=$CropRect;$result.checks.crop=$check;$passed=$passed -and $check.allPixelsIdentical -and $check.iccPresenceAndBytesMatch -and $check.colorDefinitionPreserved}
    $hashesAfter=[ordered]@{};$stable=$true
    foreach($key in $paths.Keys){$hashesAfter[$key]=(Get-FileHash -LiteralPath $paths[$key] -Algorithm SHA256).Hash.ToLowerInvariant();if($hashesAfter[$key] -ne $hashesBefore[$key]){$stable=$false}}
    $result['paths']=$paths;$result['sha256Before']=$hashesBefore;$result['sha256After']=$hashesAfter;$result['allInputsStable']=$stable;$result['integrityChecksPassed']=$true
    $passed=$passed -and $stable;$result.status=if($passed){'passed'}else{'failed'};$exitCode=if($passed){0}else{1}
} catch {$result['error']=$_.Exception.Message;$result['errorType']=$_.Exception.GetType().FullName}
$result['completedAtUtc']=[DateTime]::UtcNow.ToString('o')
$json=$result | ConvertTo-Json -Depth 12
if($reportPath -and $reportSafe){try{$parent=[IO.Path]::GetDirectoryName($reportPath);if(-not [IO.Directory]::Exists($parent)){[IO.Directory]::CreateDirectory($parent) | Out-Null};[IO.File]::WriteAllText($reportPath,$json,(New-Object Text.UTF8Encoding($false)))}catch{Write-Error -ErrorAction Continue "Could not save report: $($_.Exception.Message)";$exitCode=2}}
Write-Output $json
exit $exitCode
