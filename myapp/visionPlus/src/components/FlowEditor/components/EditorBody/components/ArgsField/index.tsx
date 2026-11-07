import React, { useEffect, useState } from 'react';
import {
  ActionButton,
  ComboBox,
  Dropdown,
  IComboBox,
  IComboBoxOption,
  IDropdownOption,
  IconButton,
  TextField,
  Toggle,
  TooltipHost,
} from '@fluentui/react';

// 单个参数渲染器：bool/select-input/select2/workdir/image/project 子类型 + tip 提醒 + regex 校验
export interface IArgsFieldProps {
  args: any;
  name: string;
  keyValue: any;
  onChange: (value: any) => void;
}

const fetchChoiceOptions = async (choiceUrl: string): Promise<IDropdownOption[]> => {
  const resp = await fetch(choiceUrl, { credentials: 'include', headers: { Accept: 'application/json' } });
  const data = await resp.json();
  const rows: any[] = Array.isArray(data) ? data : data.result || [];
  return rows.map((item: any) =>
    typeof item === 'string'
      ? { key: item, text: item }
      : { key: String(item.name ?? item.id), text: String(item.name ?? item.id) }
  );
};

const ArgsField: React.FC<IArgsFieldProps> = (props) => {
  const { args, name, keyValue, onChange } = props;
  const item_type: string = args.item_type || 'str';
  const localOptions: IDropdownOption[] = (args.choice || []).map((option: any) => ({ key: option, text: option }));
  const [remoteOptions, setRemoteOptions] = useState<IDropdownOption[]>([]);
  const [regexError, setRegexError] = useState('');

  const needRemote = item_type === 'select2' || (item_type === 'project' && localOptions.length === 0);
  useEffect(() => {
    const url: string = args.choice_url || (item_type === 'project' ? '/project_modelview/api/' : '');
    if (needRemote && url) {
      fetchChoiceOptions(url)
        .then((opts) => setRemoteOptions(opts))
        .catch(() => setRemoteOptions([]));
    }
  }, [args.choice_url, needRemote]);

  const onTextChange = (value: string) => {
    if (args.regex) {
      try {
        setRegexError(new RegExp(args.regex).test(value) ? '' : '不符合格式要求');
      } catch (e) {
        setRegexError('');
      }
    }
    onChange(value);
  };

  const tipNode = args.tip ? (
    <TooltipHost content={args.tip}>
      <IconButton iconProps={{ iconName: 'Info' }} />
    </TooltipHost>
  ) : null;

  // bool：Toggle 开关，输出 boolean
  if (args.type === 'bool') {
    const checked = keyValue === true || keyValue === 'true' || keyValue === '1';
    return (
      <div>
        <Toggle
          label={name}
          checked={checked}
          onChange={(event: React.MouseEvent<HTMLElement>, checked?: boolean) => onChange(!!checked)}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // select2 / project：站内接口拉取选项的下拉
  if (item_type === 'select2' || item_type === 'project') {
    return (
      <div>
        <Dropdown
          label={name}
          options={remoteOptions}
          selectedKey={keyValue !== undefined && keyValue !== '' ? String(keyValue) : undefined}
          onChange={(event: React.FormEvent<HTMLDivElement>, option?: IDropdownOption) => onChange(option ? String(option.key) : '')}
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // select-input：可选可填（choice 选项 + 自由输入）
  if (item_type === 'select-input') {
    return (
      <div>
        <ComboBox
          label={name}
          options={localOptions}
          selectedKey={keyValue !== undefined && keyValue !== '' ? String(keyValue) : undefined}
          text={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
          allowFreeform
          autoComplete="on"
          onChange={(event: React.FormEvent<IComboBox>, option?: IComboBoxOption, index?: number, value?: string) =>
            onChange(value !== undefined ? value : option ? option.text : '')
          }
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // workdir / image：文本框 + 平台跳转按钮
  if (item_type === 'workdir' || item_type === 'image') {
    const actionUrl =
      item_type === 'workdir'
        ? '/notebook_modelview/api/entry/jupyter?file_path=' + keyValue
        : '/docker_modelview/api/entry/docker?image=' + keyValue;
    return (
      <div>
        <TextField
          label={name}
          value={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
          onChange={(event: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, value?: string) => onTextChange(value || '')}
          errorMessage={regexError}
          required={args.require === 1}
          disabled={args.editable !== 1}
        />
        <ActionButton iconProps={{ iconName: item_type === 'workdir' ? 'FabricFolder' : 'Bug' }} onClick={() => window.open(actionUrl, '_blank')}>
          {item_type === 'workdir' ? '打开目录' : '调试镜像'}
        </ActionButton>
        <div>
          <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
          {tipNode}
        </div>
      </div>
    );
  }

  // 兜底：str/text（含 regex 校验）
  return (
    <div>
      <TextField
        label={name}
        value={keyValue !== undefined && keyValue !== null ? String(keyValue) : ''}
        onChange={(event: React.FormEvent<HTMLInputElement | HTMLTextAreaElement>, value?: string) => onTextChange(value || '')}
        errorMessage={regexError}
        required={args.require === 1}
        disabled={args.editable !== 1}
      />
      <div>
        <span dangerouslySetInnerHTML={{ __html: args.describe || '' }} />
        {tipNode}
      </div>
    </div>
  );
};

export default ArgsField;
