import AppKit
import Foundation
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let w=1080,h=1016
let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:w,pixelsHigh:h,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
let ctx=NSGraphicsContext(bitmapImageRep:rep)!
NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx
NSColor(calibratedWhite:0.07,alpha:1).setFill();NSRect(x:0,y:0,width:w,height:h).fill()
let ids=["05-window-before-v50","05-window-after-v51"]
let titles=["BEFORE • wider, farther back","REVISED • smaller, farther forward"]
for i in 0..<2 {
 let x=(i%2)*540, top=(i/2)*1016
 let attrs:[NSAttributedString.Key:Any]=[.font:NSFont.boldSystemFont(ofSize:22),.foregroundColor:NSColor.white]
 NSAttributedString(string:titles[i],attributes:attrs).draw(at:NSPoint(x:x+14,y:h-top-40))
 let img=NSImage(contentsOf:root.appendingPathComponent("frames/"+ids[i]+".png"))!
 img.draw(in:NSRect(x:x,y:h-top-1016,width:540,height:960),from:.zero,operation:.copy,fraction:1)
}
ctx.flushGraphics();NSGraphicsContext.restoreGraphicsState()
try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("frames/05-window-comparison-v52.png"))
