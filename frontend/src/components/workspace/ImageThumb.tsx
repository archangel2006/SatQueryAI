type ImageThumbProps = {
  src: string
  label?: string
  selected?: boolean
  onClick?: () => void
}

export function ImageThumb({
  src,
  label,
  selected,
  onClick,
}: ImageThumbProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`block w-[120px] overflow-hidden rounded-lg border-2 bg-surface text-left ${
        selected ? 'border-navy dark:border-accent' : 'border-border'
      }`}
    >
      <img
        src={src}
        alt=""
        className="h-[120px] w-[120px] object-cover"
        width={120}
        height={120}
      />

      {label ? (
        <div className="truncate px-2 py-1 text-[11px] text-muted">
          {label}
        </div>
      ) : null}
    </button>
  )
}