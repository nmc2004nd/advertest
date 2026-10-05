import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import { Slot } from 'radix-ui'

// Vùng chạm tối thiểu 44×44px (tech-stack.md mục 5.1).
// Vùng chạm tối thiểu 44×44px (tech-stack.md mục 5.1). Mỗi màn hình chỉ một nút `default`.
const buttonVariants = cva(
  'inline-flex min-h-11 shrink-0 cursor-pointer items-center justify-center gap-2 rounded-[10px] px-4 text-[14px] font-semibold whitespace-nowrap transition-[color,background-color,border-color,box-shadow] duration-150 ease-out outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-primary-foreground shadow-sm hover:bg-navy-hover',
        soft: 'bg-accent text-accent-foreground hover:bg-accent/70',
        destructive: 'bg-destructive text-white hover:bg-destructive/90',
        outline: 'border border-line bg-surface-solid text-foreground hover:bg-muted',
        ghost: 'text-muted-foreground hover:bg-secondary hover:text-foreground',
        link: 'text-detect-strong underline-offset-4 hover:underline',
      },
      size: {
        default: '',
        icon: 'min-w-11 px-0',
        lg: 'min-h-11 px-5 text-[14.5px]',
      },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
)

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : 'button'
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  )
}

export { Button }
