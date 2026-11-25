import AppKit
import Foundation
let root=URL(fileURLWithPath:CommandLine.arguments[1]);let ep=root.deletingLastPathComponent()
let names=["01-look","02-look","03-look","04-look","05-look","06-look","07-look","08-look","09-look","10-look","11-look","12-safehouse-preview"]
let labels=["The call runs over","Only five minutes?!","Rush out for Goji","Run to the bus","Take the driver's seat","Police lights behind","Roll and slide","Tap out. BEEP.","Dust off and go","Keep running toward Goji","Instant calm","Pilates in a safehouse"]
let times=["00:00–00:03","00:03–00:05","00:05–00:08","00:08–00:11","00:11–00:15","00:15–00:20","00:20–00:25","00:25–00:31","00:31–00:33","00:33–00:37","00:37–00:39","00:39–00:47"]
for page in 0..<3 {
 let w=1080,h=2064;let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:w,pixelsHigh:h,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 let ctx=NSGraphicsContext(bitmapImageRep:rep)!;NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx
 NSColor(calibratedWhite:0.065,alpha:1).setFill();NSRect(x:0,y:0,width:w,height:h).fill()
 for cell in 0..<4 {
  let i=page*4+cell,x=(cell%2)*540,top=(cell/2)*1032
  let title=String(format:"%02d",i+1)+"   "+times[i]
  NSAttributedString(string:title,attributes:[.font:NSFont.boldSystemFont(ofSize:22),.foregroundColor:NSColor.white]).draw(at:NSPoint(x:x+15,y:h-top-32))
  NSAttributedString(string:labels[i],attributes:[.font:NSFont.systemFont(ofSize:20),.foregroundColor:NSColor(calibratedWhite:0.80,alpha:1)]).draw(at:NSPoint(x:x+15,y:h-top-59))
  let path=root.appendingPathComponent("frames/"+names[i]+".png");let img=NSImage(contentsOf:path)!
  let bitmap=NSBitmapImageRep(data:try Data(contentsOf:path))!;let scale=min(540.0/Double(bitmap.pixelsWide),960.0/Double(bitmap.pixelsHigh))
  let iw=Double(bitmap.pixelsWide)*scale,ih=Double(bitmap.pixelsHigh)*scale
  img.draw(in:NSRect(x:Double(x)+(540-iw)/2,y:Double(h-top-1032)+(960-ih)/2,width:iw,height:ih),from:.zero,operation:.copy,fraction:1)
 }
 ctx.flushGraphics();NSGraphicsContext.restoreGraphicsState()
 let file=String(format:"%02d-%02d-storyboard.png",page*4+1,page*4+4)
 try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("frames/"+file))
}
