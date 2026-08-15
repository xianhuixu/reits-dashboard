// REITs Dashboard 定制 ECharts 构建：仅包含站点实际使用的图表与组件
import * as echarts from 'echarts/core';
import { LineChart, PieChart, RadarChart, ScatterChart, TreemapChart } from 'echarts/charts';
import {
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  GraphicComponent, AxisPointerComponent
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([
  LineChart, PieChart, RadarChart, ScatterChart, TreemapChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent,
  GraphicComponent, AxisPointerComponent,
  CanvasRenderer
]);

window.echarts = echarts;
