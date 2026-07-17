type PageHeaderProps = {
  title: string;
  description?: React.ReactNode;
  meta?: React.ReactNode;
  actions?: React.ReactNode;
  /** Optional small uppercase label above the title (e.g. "Hub"). */
  eyebrow?: string;
};

export function PageHeader({
  title,
  description,
  meta,
  actions,
  eyebrow,
}: PageHeaderProps) {
  return (
    <header className="td-page-header">
      <div className="td-page-header__main">
        {eyebrow ? <p className="td-eyebrow">{eyebrow}</p> : null}
        <h1 className="td-page-title">{title}</h1>
        {description ? <p className="td-page-desc">{description}</p> : null}
        {meta ? <div className="td-page-meta">{meta}</div> : null}
      </div>
      {actions ? <div className="td-page-header__actions">{actions}</div> : null}
    </header>
  );
}
