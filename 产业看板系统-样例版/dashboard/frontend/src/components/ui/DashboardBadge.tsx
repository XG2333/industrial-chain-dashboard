import { Badge, type BadgeProps } from 'flowbite-react';

export function DashboardBadge({
  color = 'success',
  size = 'xs',
  className,
  ...props
}: BadgeProps) {
  return <Badge color={color} size={size} className={className} {...props} />;
}
