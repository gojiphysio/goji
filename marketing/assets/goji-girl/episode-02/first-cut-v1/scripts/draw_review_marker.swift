import AppKit
import Foundation
let root=URL(fileURLWithPath:CommandLine.arguments[1])
let rep=NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:1080,pixelsHigh:1920,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
let ctx=NSGraphicsContext(bitmapImageRep:rep)!
NSGraphicsContext.saveGraphicsState();NSGraphicsContext.current=ctx
NSColor.clear.setFill();NSRect(x:0,y:0,width:1080,height:1920).fill(using:.copy)
NSColor(calibratedWhite:0.03,alpha:0.9).setFill();NSRect(x:56,y:1690,width:968,height:90).fill()
NSAttributedString(string:"STORYBOARD — MOTION PENDING",attributes:[.font:NSFont(name:"Arial-BoldMT",size:38)!, .foregroundColor:NSColor.white]).draw(at:NSPoint(x:82,y:1710))
ctx.flushGraphics();NSGraphicsContext.restoreGraphicsState()
try rep.representation(using:.png,properties:[:])!.write(to:root.appendingPathComponent("overlays/review-pending.png"))
