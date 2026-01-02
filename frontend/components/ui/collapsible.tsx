"use client"

import * as React from "react"
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible"
import { ChevronDown } from "lucide-react"
import { cn } from "@/lib/utils"

const Collapsible = CollapsiblePrimitive.Root

const CollapsibleTrigger = CollapsiblePrimitive.CollapsibleTrigger

const CollapsibleContent = CollapsiblePrimitive.CollapsibleContent

const CollapsibleHeader = React.forwardRef<
  React.ElementRef<typeof CollapsibleTrigger>,
  React.ComponentPropsWithoutRef<typeof CollapsibleTrigger> & {
    asChild?: boolean;
  }
>(({ className, children, ...props }, ref) => (
  <CollapsibleTrigger
    ref={ref}
    className={cn(
      "flex w-full items-center justify-between rounded-lg transition-colors hover:bg-muted/50 px-4 py-3 text-left font-medium group",
      className
    )}
    {...props}
  >
    {children}
    <ChevronDown className="h-4 w-4 transition-transform duration-200 group-data-[state=open]:rotate-180" />
  </CollapsibleTrigger>
))
CollapsibleHeader.displayName = "CollapsibleHeader"

export { Collapsible, CollapsibleTrigger, CollapsibleContent, CollapsibleHeader }

