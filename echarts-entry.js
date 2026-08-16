// echarts 按需定制构建入口：仅打包本站用到的图表与组件
import * as echarts from 'echarts/core';
import { LineChart, PieChart, RadarChart, ScatterChart, TreemapChart } from 'echarts/charts';
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  GraphicComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart, PieChart, RadarChart, ScatterChart, TreemapChart,
  GridComponent, TooltipComponent, LegendComponent, GraphicComponent,
  CanvasRenderer
]);

window.echarts = echarts;
