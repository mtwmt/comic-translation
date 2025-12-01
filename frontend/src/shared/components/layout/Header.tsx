// Header 元件

import { Link, useLocation } from 'react-router-dom';
import { ROUTES, APP_CONFIG } from '../../constants/config';

export function Header() {
  const location = useLocation();

  const isActive = (path: string) => location.pathname === path;

  return (
    <div className="navbar bg-base-100 shadow-lg">
      <div className="flex-1">
        <Link to={ROUTES.HOME} className="btn btn-ghost text-xl">
          {APP_CONFIG.name}
        </Link>
      </div>
      <div className="flex-none">
        <ul className="menu menu-horizontal px-1">
          <li>
            <Link
              to={ROUTES.HOME}
              className={isActive(ROUTES.HOME) ? 'active' : ''}
            >
              翻譯
            </Link>
          </li>
          <li>
            <Link
              to={ROUTES.SETTINGS}
              className={isActive(ROUTES.SETTINGS) ? 'active' : ''}
            >
              設定
            </Link>
          </li>
        </ul>
      </div>
    </div>
  );
}
