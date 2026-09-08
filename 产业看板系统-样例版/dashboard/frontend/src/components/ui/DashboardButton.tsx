import { Button, type ButtonProps } from 'flowbite-react';

export function DashboardButton({
  size = 'sm',
  color = 'light',
  className,
  ...props
}: ButtonProps) {
  return <Button size={size} color={color} className={className} {...props} />;
}
